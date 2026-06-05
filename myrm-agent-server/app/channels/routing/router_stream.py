"""Consume AgentExecutor event streams: progress, streaming text, interactive approvals.

[POS]
RouterStreamMixin composed into AgentRouter (router.py) via multiple inheritance;
methods constrain self via RouterStreamHost. Placeholder throttle interval logic in
router_stream_throttle.py (pure function, unit-testable). Logger name consistent with router package.
"""

from __future__ import annotations

import dataclasses
import logging
import time

from myrm_agent_harness.infra.tracing import get_current_trace_id, trace_context
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.i18n import channel_t, get_text
from app.channels.routing.placeholder_strategy import DeferredPlaceholder
from app.channels.routing.router_constants import (
    _MIN_PROGRESS_INTERVAL,
)
from app.channels.routing.router_host import RouterStreamHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.routing.router_stream_throttle import (
    should_skip_throttled_placeholder_edit,
)
from app.channels.types import (
    InboundMessage,
    MessagePriority,
    OutboundMessage,
    ProgressUpdate,
    StreamingText,
    TopicContext,
)

logger = logging.getLogger("myrm.channels.routing.stream")


class RouterStreamMixin:
    """Mixin: throttled placeholder edits and approval message tracking during execute_stream."""

    async def _mark_deferred_placeholder_activity(self: RouterStreamHost, state_key: str) -> None:
        active = self._active_tasks.get(state_key)
        deferred = active.deferred_placeholder if active else None
        if isinstance(deferred, DeferredPlaceholder):
            await deferred.mark_activity()
            if active and deferred.placeholder_id:
                active.placeholder_id = deferred.placeholder_id

    async def _consume_executor_stream(
        self: RouterStreamHost,
        msg: InboundMessage,
        user_id: str,
        state_key: str,
        chat_id: str,
        *,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        topic_context: TopicContext | None = None,
    ) -> tuple[OutboundMessage | None, float]:
        """Consume execute_stream with unified StreamCoordinator and production-grade protections.

        Uses StreamCoordinator to orchestrate all streaming optimizations:
        - IncrementalEditor: tracks content changes for decision logic
        - AdaptiveThrottler: adapts update frequency to network conditions
        - BlockChunker: intelligent chunking with code fence protection
        - GracefulDegradation: smoothly reduces update frequency on failures
        - SessionRateLimiter: prevents single session from flooding updates

        Returns (result, last_progress_at) so the caller can enforce
        a minimum gap before the final edit.
        """
        last_progress_at = 0.0
        result: OutboundMessage | None = None

        last_stream_at = 0.0
        edit_failures = 0
        should_fallback_to_new_message = False
        has_pending_approval = False

        metrics_key = f"{msg.channel}:{chat_id}:{msg.message_id}"
        trace_id = get_current_trace_id() or ""
        stream_state_key = routing_session_key(msg.channel, chat_id)
        self._stream_metrics.start_session(metrics_key, trace_id)
        self._progress_estimator.start_session(metrics_key, msg.content)

        async for event in self._executor.execute_stream(
            msg,
            user_id,
            cancel_token=cancel_token,
            steering_token=steering_token,
            topic_context=topic_context,
        ):
            if isinstance(event, ProgressUpdate):
                await self._mark_deferred_placeholder_activity(stream_state_key)
                if event.quick_replies:
                    approval_mid = await self._send_interactive_progress(msg, chat_id, event)
                    if approval_mid:
                        session_key = routing_session_key(msg.channel, chat_id)
                        self._approval_msg_ids[session_key] = approval_mid
                    has_pending_approval = True
                    last_progress_at = time.monotonic()
                    continue

                new_ts = await self._try_throttled_edit(
                    self._resolve_live_placeholder_id(state_key),
                    event.label,
                    last_progress_at,
                    _MIN_PROGRESS_INTERVAL,
                    msg.channel,
                    chat_id,
                )
                if new_ts is not None:
                    last_progress_at = new_ts

            elif isinstance(event, StreamingText):
                await self._mark_deferred_placeholder_activity(stream_state_key)
                if should_fallback_to_new_message:
                    continue

                with trace_context(
                    "myrm.channels.stream",
                    "stream_update",
                    {
                        "session_key": metrics_key,
                        "trace_id": trace_id,
                        "content_length": len(event.text),
                    },
                ) as span:
                    decision = self._stream_coordinator.should_send_update(metrics_key, event.text, is_final=False)
                    self._stream_metrics.record_decision(metrics_key, decision.reason)
                    span.set_attribute("decision.should_send", decision.should_send)
                    span.set_attribute("decision.reason", decision.reason)

                    if not decision.should_send:
                        logger.debug(
                            "skip_stream_update session_key=%s reason=%s trace_id=%s",
                            metrics_key,
                            decision.reason,
                            trace_id,
                        )
                        span.add_event("update_skipped", {"reason": decision.reason})
                        continue

                    if not self._session_rate_limiter.can_update(metrics_key):
                        logger.warning(
                            "session_rate_limit_exceeded session_key=%s trace_id=%s update_count=%d",
                            metrics_key,
                            trace_id,
                            self._session_rate_limiter.get_update_count(metrics_key),
                        )
                        span.add_event("rate_limit_exceeded")
                        continue

                    self._session_rate_limiter.record_update(metrics_key)

                    progress_info = self._progress_estimator.estimate_progress(metrics_key, len(event.text))
                    display_text = event.text
                    if progress_info and progress_info.percentage < 95:
                        remaining_str = f" (~{progress_info.remaining_seconds}s left)" if progress_info.remaining_seconds else ""
                        display_text = f"{event.text}\n\n[{progress_info.percentage}%{remaining_str}]"
                        span.set_attribute("progress.percentage", progress_info.percentage)

                    span.add_event("api_call_start")
                    live_placeholder = self._resolve_live_placeholder_id(state_key)
                    success = await self._try_edit_with_retry(
                        msg.channel,
                        chat_id,
                        live_placeholder,
                        display_text,
                        metrics_key,
                        len(event.text),
                        msg=msg,
                    )
                    span.add_event("api_call_end", {"success": success})
                    span.set_attribute("api.success", success)

                    is_first = last_stream_at == 0.0
                    self._stream_metrics.record_edit(metrics_key, len(event.text), success, is_first=is_first)

                    if success:
                        last_stream_at = time.monotonic()
                        edit_failures = 0
                    else:
                        edit_failures += 1
                        if edit_failures >= 3:
                            should_fallback_to_new_message = True
                            logger.warning(
                                "stream_edit_failed_fallback session_key=%s trace_id=%s consecutive_failures=%d",
                                metrics_key,
                                trace_id,
                                edit_failures,
                            )
                            span.add_event(
                                "fallback_to_new_message",
                                {"consecutive_failures": edit_failures},
                            )

            elif isinstance(event, OutboundMessage):
                result = dataclasses.replace(
                    event,
                    thread_id=msg.thread_id,
                    reply_to_id=(
                        (msg.message_id or str(msg.metadata["message_id"]))
                        if msg.is_group and (msg.message_id or msg.metadata.get("message_id"))
                        else event.reply_to_id
                    ),
                )
                if should_fallback_to_new_message:
                    live_placeholder = self._resolve_live_placeholder_id(state_key)
                    if live_placeholder:
                        await self._fx.cleanup_placeholder(
                            msg.channel,
                            chat_id,
                            live_placeholder,
                            " [Streaming interrupted]",
                        )

        self._stream_metrics.end_session(metrics_key)
        self._stream_coordinator.cleanup(metrics_key)
        self._progress_estimator.cleanup(metrics_key)

        if has_pending_approval:
            result = None

        last_edit_at = max(last_progress_at, last_stream_at)
        if result:
            logger.info(
                "stream_completed session_key=%s trace_id=%s content_length=%d",
                metrics_key,
                trace_id,
                len(result.content),
            )
        else:
            logger.warning(
                "stream_completed_without_result session_key=%s trace_id=%s",
                metrics_key,
                trace_id,
            )
        return result, last_edit_at

    _EMOJI_APPROVAL_HINT = "\n\n\U0001f44d Allow once  ·  \u267e\ufe0f Allow always  ·  \U0001f44e Deny"

    async def _send_interactive_progress(
        self: RouterStreamHost,
        msg: InboundMessage,
        chat_id: str,
        progress: ProgressUpdate,
    ) -> str | None:
        """Send a standalone message with quick_replies for interactive progress.

        Used for tool approval prompts: the text shows the approval request,
        and quick_replies provide /approve and /deny buttons. For reaction-
        capable channels, also append a three-tier reaction hint mirroring the
        emoji decision model recognised by ``parse_approval_command``:
        👍 once · ♾️ always · 👎 deny.

        Returns the platform message_id for later editing (approval lifecycle).
        """
        content = progress.label
        channel_obj = self._bus.get_channel(msg.channel)
        if channel_obj and getattr(channel_obj.capabilities, "reactions", False):
            content += self._EMOJI_APPROVAL_HINT

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            quick_replies=progress.quick_replies,
            thread_id=msg.thread_id,
            reply_to_id=(
                (msg.message_id or str(msg.metadata["message_id"]))
                if msg.is_group and (msg.message_id or msg.metadata.get("message_id"))
                else msg.reply_to_id
            ),
            priority=MessagePriority.SYSTEM,
        )
        return await self._bus.send_tracked(reply)

    async def _try_throttled_edit(
        self: RouterStreamHost,
        placeholder_id: str | None,
        content: str,
        last_edit_at: float,
        min_interval: float,
        channel: str,
        chat_id: str,
    ) -> float | None:
        """Try to edit placeholder with throttling.

        Returns new timestamp if edited, None if skipped/no placeholder.
        """
        if not placeholder_id:
            return None

        now = time.monotonic()
        if should_skip_throttled_placeholder_edit(now, last_edit_at, min_interval):
            return None

        await self._fx.edit_progress(channel, chat_id, placeholder_id, content)
        return now

    async def _try_edit_with_retry(
        self: RouterStreamHost,
        channel: str,
        chat_id: str,
        placeholder_id: str | None,
        content: str,
        metrics_key: str,
        full_text_length: int,
        max_retries: int = 3,
        *,
        msg: InboundMessage | None = None,
    ) -> bool:
        """Try to edit with RetryPolicy and circuit breaker protection.

        Uses RetryPolicy for clean retry logic with span tracing.

        Args:
            channel: Channel identifier
            chat_id: Chat identifier
            placeholder_id: Placeholder message ID
            content: Content to send (may include progress UI)
            metrics_key: Session key for metrics
            full_text_length: Full text length for metrics
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            True if successful, False after all retries exhausted or circuit open
        """
        if not placeholder_id:
            return False

        with trace_context(
            "myrm.channels.stream",
            "edit_with_retry",
            {
                "session_key": metrics_key,
                "channel": channel,
                "content_length": len(content),
                "full_text_length": full_text_length,
                "max_retries": max_retries,
            },
        ) as span:

            async def edit_operation() -> bool:
                """Single edit operation with metrics and degradation recording."""
                edit_start = time.perf_counter()
                span.add_event("api_call_start")

                success = await self._fx.edit_progress(channel, chat_id, placeholder_id, content)
                edit_latency_s = time.perf_counter() - edit_start
                edit_latency_ms = edit_latency_s * 1000

                span.add_event(
                    "api_call_end",
                    {
                        "latency_ms": edit_latency_ms,
                        "success": success,
                    },
                )
                span.set_attribute("api.latency_ms", edit_latency_ms)

                self._stream_coordinator.record_send_latency(edit_latency_s)
                self._stream_metrics.record_api_latency(metrics_key, edit_latency_ms)

                full_text_bytes = full_text_length * 3
                self._stream_metrics.record_transmission(metrics_key, full_text_bytes, full_text_bytes)

                if success:
                    self._degradation_controller.record_success()
                else:
                    self._degradation_controller.record_failure()
                    raise RuntimeError("Edit operation returned False")

                return success

            async def on_retry(attempt: int, delay: float) -> None:
                """UI feedback callback for retry attempts."""
                retry_suffix = (
                    get_text(
                        msg,
                        "placeholder_retrying",
                        attempt=attempt,
                        max_retries=max_retries,
                    )
                    if msg is not None
                    else channel_t(
                        None,
                        "placeholder_retrying",
                        attempt=attempt,
                        max_retries=max_retries,
                    )
                )
                retry_content = f"{content}{retry_suffix}"
                try:
                    await self._fx.edit_progress(channel, chat_id, placeholder_id, retry_content)
                except Exception:
                    pass
                span.add_event(
                    "retry_feedback_shown",
                    {
                        "attempt": attempt,
                        "delay_seconds": delay,
                    },
                )

            result = await self._retry_policy.execute(
                operation=edit_operation,
                session_key=metrics_key,
                on_retry_callback=on_retry,
            )

            span.set_attribute("final_success", result.success)
            span.set_attribute("final_attempts", result.attempts)
            span.set_attribute("total_delay_s", result.total_delay)

            return result.success
