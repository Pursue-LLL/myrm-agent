"""Async message bus for channel routing.

Decouples message producers (Cron executor, Agent runtime) from
consumers (Channel providers). Uses ``asyncio.PriorityQueue`` for
priority-based dispatch with back-pressure.


[INPUT]
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.core.base::BaseChannel (POS: channel abstract base class)
- channels.reliability.retry::send_with_retry (POS: async retry utility with exponential backoff)
- channels.reliability.rate_limiter::ChannelRateLimiter (POS: per-channel rate limiter)
- services.risk.detection::RiskDetectionService (POS: stateful risk detection engine with compiled regex cache)

[OUTPUT]
- MessageBus: async message bus managing outbound/inbound queues and channel registration
- MessageBus.send_tracked(): bypasses queue for direct send, returns message_id; on failure persists to DLQ and invokes on_permanent_failure
- MessageBus._record_outbound_failure(): shared DLQ + permanent-failure callback for sync and async send paths
- MessageBus.edit_channel_message(): edits a sent message (for updating approval status)
- downgrade_components: interactive component downgrade (appends text fallback when channel lacks support)
- _apply_outbound_risk_gate: content safety detection before send (reuses RiskDetectionService)

[POS]
Message routing hub. Producers call publish_outbound; the bus dispatches by priority
to the target channel (SYSTEM > NORMAL > BULK). Inbound messages enter the _inbound
queue via channel _emit_inbound callbacks, consumed by AgentRouter.

Outbound messages are auto-downgraded before dispatch for channels lacking interactive
component support: components are rendered as text appended to content; quick_replies
only downgrade ``required=True`` items, silently dropping non-required ones.
"""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from myrm_agent_harness.infra.delivery.dead_letter import DeadLetterQueue
from myrm_agent_harness.infra.delivery.notification_ledger import PermanentFailureNotificationLedger
from myrm_agent_harness.infra.delivery.storage import (
    QueuedDelivery,
    delete_failed_delivery,
    move_to_failed,
)

from app.channels.core.base import BaseChannel
from app.channels.core.events import EventEmitter
from app.channels.i18n import channel_t, get_locale_from_metadata
from app.channels.reliability.rate_limiter import (
    TokenBucket,
    create_limiter,
)
from app.channels.reliability.retry import send_with_retry
from app.channels.types import (
    ActionButton,
    ChannelStatus,
    ComponentRow,
    CorrelationContext,
    InboundMessage,
    OutboundMessage,
    SelectMenu,
    render_components_as_text,
    render_quick_replies_as_text,
)

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE_SIZE = 256
_DEFAULT_DLQ_ALERT_THRESHOLD = 100

# Global context var for implicit routing lineage across async tasks
_correlation_context_var: contextvars.ContextVar[CorrelationContext | None] = contextvars.ContextVar(
    "correlation_context", default=None
)


def set_correlation_context(
    ctx: CorrelationContext | None,
) -> contextvars.Token[CorrelationContext | None]:
    """Set the current correlation context for the async execution flow."""
    return _correlation_context_var.set(ctx)


def get_correlation_context() -> CorrelationContext | None:
    """Get the current correlation context for the async execution flow."""
    return _correlation_context_var.get()


def _apply_correlation_context(msg: OutboundMessage) -> OutboundMessage:
    """Apply the active correlation context to an outbound message, correcting drifted routes."""
    ctx = msg.correlation_context or get_correlation_context()
    if not ctx:
        return msg

    # If the message already has the exact same context, no need to replace
    if msg.correlation_context == ctx and msg.channel == ctx.channel and msg.recipient_id == ctx.chat_id:
        return msg

    # Correct the routing using the immutable lineage context
    return dataclasses.replace(
        msg,
        channel=ctx.channel,
        recipient_id=ctx.chat_id or msg.recipient_id,
        correlation_context=ctx,
    )


def _apply_outbound_risk_gate(msg: OutboundMessage) -> OutboundMessage:
    """Apply risk detection to outbound message content before sending to IM channels.

    Uses the global RiskDetectionService (compiled regex cache, <1ms).
    If blocked, replaces content with a safe i18n message and fires audit asynchronously.
    Returns the original message unchanged when no rules match or service has zero rules.
    """
    if not msg.content:
        return msg

    from app.services.risk.detection import get_detection_service

    service = get_detection_service()
    if service.rule_count == 0:
        return msg

    result = service.detect(msg.content)
    if not result.blocked:
        return msg

    locale = get_locale_from_metadata(msg.metadata)
    blocked_content = channel_t(locale, "risk_outbound_blocked")

    logger.info(
        "Outbound risk gate blocked message on channel '%s': rules=%s",
        msg.channel,
        [m.display_name for m in result.matches],
    )

    asyncio.ensure_future(_record_outbound_risk_hits(result.matches, msg))

    return dataclasses.replace(msg, content=blocked_content)


async def _record_outbound_risk_hits(
    matches: tuple[object, ...], msg: OutboundMessage
) -> None:
    """Fire-and-forget: persist risk hit records for outbound blocked messages."""
    try:
        from app.platform_utils import get_session_factory
        from app.services.risk.detection import get_detection_service

        service = get_detection_service()
        session_factory = get_session_factory()
        async with session_factory() as db:
            await service.record_hits(
                db,
                matches,  # type: ignore[arg-type]
                trace_id=str(uuid.uuid4()),
                session_id=msg.recipient_id,
            )
            await db.commit()
    except Exception:
        logger.debug("Failed to record outbound risk hits (non-critical)", exc_info=True)


def create_default_message_bus(
    dlq_dir: Path | None = None,
    on_permanent_failure: (Callable[[QueuedDelivery, str], Awaitable[None]] | None) = None,
    **kwargs: object,
) -> MessageBus:
    """Create a MessageBus with default configuration.

    This is a convenience factory function for users of the harness framework
    who want to quickly set up a message bus with DLQ support.
    """
    return MessageBus(
        dlq_dir=dlq_dir,
        on_permanent_failure=on_permanent_failure,
        **kwargs,
    )


def downgrade_components(msg: OutboundMessage, channel: BaseChannel) -> OutboundMessage:
    """Downgrade interactive components to text when the channel lacks native support.

    Returns the original message unchanged if no downgrade is needed.

    Per-row granularity: a row containing SelectMenu items is downgraded
    independently from rows containing only ActionButton items, allowing
    channels that support buttons but not select menus to keep the buttons.

    For quick_replies, only ``required=True`` items are rendered as text
    fallback (e.g. approval prompts). Non-required items (e.g. suggestions)
    are silently dropped to avoid cluttering text-only channels.

    **Locale support**: Reads ``msg.metadata["locale"]`` (default: "en" for framework
    internationalization compliance). Business layer should inject user's preferred
    locale via metadata (e.g., from UserConfig or browser Accept-Language header).
    Fallback messages are rendered in the specified language:
    - "zh": "item", "reply countselect"
    - "en": "Options", "Reply with a number to select"

    **Logging**: When components are downgraded, an INFO-level log is emitted:
    ``Downgrading components for channel 'whatsapp': buttons, quick_replies(2) → text fallback``

    **Example**::

        # Original message with buttons
        msg = OutboundMessage(
            channel="whatsapp",
            recipient_id="user123",
            content="Choose an option:",
            components=(
                (ActionButton(label="Approve", action_id="approve"),),
            ),
        )

        # After downgrade (WhatsApp doesn't support buttons)
        result = downgrade_components(msg, whatsapp_channel)
        # result.content = "Choose an option:\\n\\n• Approve → /approve"
        # result.components = ()
    """
    if not msg.components and not msg.quick_replies and not msg.media:
        return msg

    caps = channel.capabilities
    locale = get_locale_from_metadata(msg.metadata)
    changed = False
    fallback_parts: list[str] = []
    kept_rows: list[ComponentRow] = []
    downgraded_types: list[str] = []

    for row in msg.components:
        has_select = any(isinstance(c, SelectMenu) for c in row)
        has_button = any(isinstance(c, ActionButton) for c in row)

        if has_select and not caps.select_menus:
            text = render_components_as_text((row,), locale=locale)
            if text:
                fallback_parts.append(text)
            changed = True
            if "select_menus" not in downgraded_types:
                downgraded_types.append("select_menus")
        elif has_button and not caps.buttons:
            text = render_components_as_text((row,), locale=locale)
            if text:
                fallback_parts.append(text)
            changed = True
            if "buttons" not in downgraded_types:
                downgraded_types.append("buttons")
        else:
            kept_rows.append(row)

    keep_quick_replies = msg.quick_replies
    if msg.quick_replies and not caps.quick_replies:
        required_qrs = tuple(qr for qr in msg.quick_replies if qr.required)
        if required_qrs:
            text = render_quick_replies_as_text(required_qrs, locale=locale)
            if text:
                fallback_parts.append(text)
            downgraded_types.append(f"quick_replies({len(required_qrs)})")
        keep_quick_replies = ()
        changed = True

    keep_media = msg.media
    if msg.media:
        media_fallback_parts = []
        keep_media_list = []

        from app.channels.types.messages import MediaType

        for m in msg.media:
            is_document = m.media_type == MediaType.DOCUMENT
            should_strip = (is_document and not caps.file_upload) or (not is_document and not caps.media)

            if should_strip:
                if m.url:
                    media_fallback_parts.append(f"[{m.media_type.value.capitalize()}: {m.url}]")
                elif m.path:
                    media_fallback_parts.append(f"[{m.media_type.value.capitalize()} attachment omitted (unsupported channel)]")
            else:
                keep_media_list.append(m)

        if media_fallback_parts:
            fallback_parts.extend(media_fallback_parts)
            downgraded_types.append(f"media({len(media_fallback_parts)})")
            changed = True

        keep_media = tuple(keep_media_list)

    if not changed:
        return msg

    logger.info(
        "Downgrading components/media for channel '%s': %s → text fallback",
        channel.name,
        ", ".join(downgraded_types),
    )

    suffix = "\n\n" + "\n".join(fallback_parts) if fallback_parts else ""
    return dataclasses.replace(
        msg,
        content=msg.content + suffix,
        components=tuple(kept_rows),
        quick_replies=keep_quick_replies,
        media=keep_media,
    )


class MessageBus:
    """Async message bus with outbound dispatch and inbound collection."""

    def __init__(
        self,
        max_queue_size: int = _DEFAULT_QUEUE_SIZE,
        dlq_dir: Path | None = None,
        dlq_alert_cooldown_sec: int = 3600,
        on_permanent_failure: (Callable[[QueuedDelivery, str], Awaitable[None]] | None) = None,
        notification_ledger: PermanentFailureNotificationLedger | None = None,
    ) -> None:
        self._max_queue_size = max_queue_size
        self._outbound: asyncio.PriorityQueue[tuple[int, int, OutboundMessage]] | None = None
        self._outbound_seq = 0
        self._inbound: asyncio.Queue[InboundMessage] | None = None
        self._channels: dict[str, BaseChannel] = {}
        self._limiters: dict[str, TokenBucket] = {}
        self._last_send_times: dict[str, float] = {}
        self._dispatch_task: asyncio.Task[None] | None = None
        self._running = False
        self._dlq_dir = dlq_dir
        self._dlq: DeadLetterQueue | None = None
        self.events = EventEmitter("MessageBus")
        self._dlq_alert_cooldown_sec = dlq_alert_cooldown_sec
        self._last_dlq_alert_times: dict[str, float] = {}
        self.on_permanent_failure = on_permanent_failure
        self._notification_ledger = notification_ledger
        self._presync_notified_delivery_ids: set[str] = set()

    def _is_permanent_failure_already_notified(self, delivery_id: str) -> bool:
        if delivery_id in self._presync_notified_delivery_ids:
            return True
        if self._dlq is not None and delivery_id in self._dlq._permanent_failure_notified_ids:
            return True
        if self._notification_ledger is not None and self._notification_ledger.was_notified(delivery_id):
            self._presync_notified_delivery_ids.add(delivery_id)
            if self._dlq is not None:
                self._dlq.mark_permanent_failure_notified(delivery_id)
            return True
        return False

    def _mark_permanent_failure_notified(self, delivery_id: str) -> None:
        self._presync_notified_delivery_ids.add(delivery_id)
        if self._dlq is not None:
            self._dlq.mark_permanent_failure_notified(delivery_id)
        elif self._notification_ledger is not None:
            self._notification_ledger.mark_notified(delivery_id)

    async def _dlq_enqueue(
        self,
        channel: str,
        recipient: str,
        content: dict[str, object],
        priority: int = 2,
    ) -> str:
        """Callback for DeadLetterQueue to re-enqueue a failed message."""
        msg = OutboundMessage.from_dict(content)
        await self.publish_outbound(msg)

        # Track metric if channel exists
        ch = self._channels.get(channel)
        if ch and hasattr(ch, "metrics"):
            ch.metrics.record_dlq_retry_success()

        return "enqueued"

    def _dlq_max_retries(self) -> int:
        if self._dlq is not None:
            return self._dlq.max_retries
        return 3

    async def _emit_dlq_threshold_if_needed(self, channel_name: str) -> None:
        if self._dlq is None or self._dlq_dir is None:
            return
        dlq_count = await self._dlq.get_failed_count()
        if dlq_count < _DEFAULT_DLQ_ALERT_THRESHOLD:
            return
        now = time.time()
        last_alert_time = self._last_dlq_alert_times.get(channel_name, 0.0)
        if now - last_alert_time < self._dlq_alert_cooldown_sec:
            logger.debug(
                "DLQ threshold exceeded for '%s', but alert is on cooldown",
                channel_name,
            )
            return
        self._last_dlq_alert_times[channel_name] = now
        self.events.emit(
            "DLQ_THRESHOLD_EXCEEDED",
            {"count": dlq_count, "channel": channel_name},
        )

    async def _record_outbound_failure(
        self,
        msg: OutboundMessage,
        error: str,
        *,
        retries_exhausted: bool,
    ) -> None:
        """Persist a failed outbound send to DLQ and optionally notify permanent failure."""
        if self._dlq_dir is None and self.on_permanent_failure is None:
            return

        max_retries = self._dlq_max_retries()
        delivery = QueuedDelivery(
            id=uuid.uuid4().hex,
            channel=msg.channel,
            recipient=msg.recipient_id,
            content=msg.to_dict(),
            enqueued_at=time.time(),
            priority=msg.priority.value,
            retry_count=max_retries if retries_exhausted else 0,
            last_attempt_at=time.time(),
            last_error=error,
            failed_at=time.time() if retries_exhausted else None,
        )

        if self._dlq_dir is not None:
            try:
                await move_to_failed(delivery, base_dir=self._dlq_dir)
                logger.debug("Message added to DLQ for channel '%s'", msg.channel)
                await self._emit_dlq_threshold_if_needed(msg.channel)
            except Exception as dlq_e:
                logger.error(
                    "Failed to save message to DLQ for channel '%s': %s",
                    msg.channel,
                    dlq_e,
                )

        if retries_exhausted and self.on_permanent_failure is not None:
            if self._is_permanent_failure_already_notified(delivery.id):
                return
            try:
                await self.on_permanent_failure(delivery, error)
                self._mark_permanent_failure_notified(delivery.id)
            except Exception as cb_e:
                logger.error(
                    "Error in on_permanent_failure callback for channel '%s': %s",
                    msg.channel,
                    cb_e,
                )

    def _ensure_queues(self) -> None:
        if self._outbound is None:
            self._outbound = asyncio.PriorityQueue(maxsize=self._max_queue_size)
        if self._inbound is None:
            self._inbound = asyncio.Queue(maxsize=self._max_queue_size)

    def register_channel(self, channel: BaseChannel) -> None:
        """Register a channel provider for outbound dispatch."""
        if channel.name in self._channels:
            logger.warning("Channel '%s' already registered, replacing", channel.name)
        self._channels[channel.name] = channel
        self._limiters[channel.name] = create_limiter(channel.name)
        channel.set_inbound_handler(self._handle_inbound)
        logger.debug("Channel registered: %s", channel.name)

    def unregister_channel(self, name: str) -> BaseChannel | None:
        """Remove a channel from the bus. Returns the removed channel or None."""
        channel = self._channels.pop(name, None)
        self._limiters.pop(name, None)
        self._last_send_times.pop(name, None)
        if channel:
            channel._inbound_handler = None
            logger.debug("Channel unregistered: %s", name)
        return channel

    def get_channel(self, name: str) -> BaseChannel | None:
        return self._channels.get(name)

    @property
    def registered_channels(self) -> list[str]:
        return list(self._channels.keys())

    @property
    def channels(self) -> dict[str, BaseChannel]:
        """Read-only access to registered channels (used by Gateway)."""
        return self._channels

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Enqueue an outbound message for priority-based delivery."""
        self._ensure_queues()
        assert self._outbound is not None
        msg = _apply_correlation_context(msg)
        try:
            self._outbound_seq += 1
            self._outbound.put_nowait((msg.priority, self._outbound_seq, msg))
        except asyncio.QueueFull:
            logger.warning("Outbound queue full, dropping message for channel '%s'", msg.channel)

    async def send_tracked(self, msg: OutboundMessage) -> str | None:
        """Send a message directly (bypassing the queue) and return its platform message_id.

        Used for messages that need lifecycle management (e.g. approval prompts
        that will be edited after the user responds). Applies the same retry
        policy as the dispatch loop for reliability.
        """
        msg = _apply_correlation_context(msg)
        channel = self._channels.get(msg.channel)
        if not channel:
            logger.warning("No channel registered for '%s', cannot send_tracked", msg.channel)
            return None
        if channel.status == ChannelStatus.DISABLED:
            logger.debug("Channel '%s' is disabled, cannot send_tracked", msg.channel)
            return None
        msg = downgrade_components(msg, channel)
        msg = _apply_outbound_risk_gate(msg)

        rate_limit = channel.capabilities.send_rate_limit
        if rate_limit > 0:
            last_send = self._last_send_times.get(msg.channel, 0.0)
            elapsed = time.monotonic() - last_send
            if elapsed < rate_limit:
                await asyncio.sleep(rate_limit - elapsed)

        t0 = time.monotonic()
        try:
            if await self._try_cp_egress(msg):
                latency_ms = (time.monotonic() - t0) * 1000
                channel.activity.record_outbound(latency_ms=latency_ms)
                if rate_limit > 0:
                    self._last_send_times[msg.channel] = time.monotonic()
                return "cp_egress"

            result = await send_with_retry(
                channel.send,
                msg,
                config=channel.retry_config,
                should_retry=channel.should_retry,
                extract_retry_after=channel.extract_retry_after,
                label=f"send_tracked:{msg.channel}",
            )
            latency_ms = (time.monotonic() - t0) * 1000
            channel.activity.record_outbound(latency_ms=latency_ms)
            if rate_limit > 0:
                self._last_send_times[msg.channel] = time.monotonic()
            return result
        except Exception as e:
            channel.activity.record_error()
            logger.warning("Channel '%s' send_tracked failed after retries: %s", msg.channel, e)
            await self._record_outbound_failure(msg, str(e), retries_exhausted=True)
            return None

    async def edit_channel_message(self, channel_name: str, chat_id: str, message_id: str, content: str) -> bool:
        """Edit a previously sent message on a channel. Returns True if successful."""
        from app.services.channels.cp_egress_client import send_via_control_plane, should_route_via_control_plane

        if should_route_via_control_plane(channel_name, None):
            tenant_id = ""
            ctx = get_correlation_context()
            if ctx and ctx.user_id:
                tenant_id = ctx.user_id
            result = await send_via_control_plane(
                channel=channel_name,
                chat_id=chat_id,
                content=content,
                tenant_id=tenant_id,
                update_message_id=message_id,
            )
            return result is not None

        channel = self._channels.get(channel_name)
        if not channel:
            return False
        try:
            await channel.edit_message(chat_id, message_id, content)
            return True
        except Exception as e:
            logger.warning("Channel '%s' edit_message failed: %s", channel_name, e)
            return False

    async def consume_inbound(self) -> InboundMessage:
        """Block until an inbound message is available."""
        self._ensure_queues()
        assert self._inbound is not None
        return await self._inbound.get()

    async def get_dlq_messages(self) -> list[QueuedDelivery]:
        """Get a list of failed messages from the DLQ."""
        if self._dlq:
            return await self._dlq.get_failed_deliveries()
        return []

    async def retry_dlq_message(self, message_id: str) -> bool:
        """Retry a failed message from the DLQ by re-enqueueing it."""
        if self._dlq:
            return await self._dlq.manual_retry(message_id)
        return False

    async def retry_all_dlq_messages(self) -> int:
        """Retry all failed messages from the DLQ."""
        if self._dlq:
            return await self._dlq.manual_retry_all()
        return 0

    async def delete_dlq_message(self, message_id: str) -> bool:
        """Delete a failed message from the DLQ."""
        if self._dlq_dir:
            return await delete_failed_delivery(message_id, base_dir=self._dlq_dir)
        return False

    async def _handle_inbound(self, msg: InboundMessage) -> None:
        """Callback for channels to publish inbound messages."""
        self._ensure_queues()
        assert self._inbound is not None
        try:
            self._inbound.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Inbound queue full, dropping message from channel '%s'", msg.channel)

    async def start(self) -> None:
        """Start the outbound dispatch loop."""
        if self._running:
            return
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        if self._dlq_dir:
            self._dlq = DeadLetterQueue(
                enqueue_fn=self._dlq_enqueue,
                base_dir=self._dlq_dir,
                on_permanent_failure=self.on_permanent_failure,
                notification_ledger=self._notification_ledger,
            )
            for delivery_id in self._presync_notified_delivery_ids:
                self._dlq.mark_permanent_failure_notified(delivery_id)
            self._presync_notified_delivery_ids.clear()
            await self._dlq.start()
        logger.info("MessageBus started (channels: %s)", ", ".join(self._channels) or "none")

    async def stop(self) -> None:
        """Stop the dispatch loop."""
        self._running = False
        if self._dlq:
            await self._dlq.stop()
            self._dlq = None
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("MessageBus dispatch task failed during stop: %s", e)
            self._dispatch_task = None
        self._outbound = None
        self._inbound = None
        self._dlq = None
        logger.info("MessageBus stopped")

    async def _try_cp_egress(self, msg: OutboundMessage) -> bool:
        """Route outbound via Control Plane when running in SaaS sandbox."""
        from app.services.channels.cp_egress_client import send_via_control_plane, should_route_via_control_plane

        meta = msg.metadata if isinstance(msg.metadata, dict) else None
        if not should_route_via_control_plane(msg.channel, meta):
            return False

        tenant_id = msg.user_id or ""
        ctx = msg.correlation_context or get_correlation_context()
        if ctx and ctx.user_id:
            tenant_id = ctx.user_id

        update_id = None
        if meta and meta.get("update_message_id"):
            update_id = str(meta["update_message_id"])

        result = await send_via_control_plane(
            channel=msg.channel,
            chat_id=msg.recipient_id,
            content=msg.content,
            tenant_id=tenant_id,
            reply_to_message_id=msg.reply_to_id,
            update_message_id=update_id,
            thread_id=msg.thread_id,
        )
        return result is not None

    async def _dispatch_loop(self) -> None:
        """Continuously dequeue outbound messages and route to channels (priority order)."""
        self._ensure_queues()
        assert self._outbound is not None
        while self._running:
            try:
                _priority, _seq, msg = await asyncio.wait_for(self._outbound.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            channel = self._channels.get(msg.channel)
            if not channel:
                if await self._try_cp_egress(msg):
                    continue
                logger.warning("No channel registered for '%s', dropping message", msg.channel)
                continue
            if channel.status == ChannelStatus.DISABLED:
                logger.debug("Channel '%s' is disabled, dropping message", msg.channel)
                continue

            if channel.health.circuit_open:
                remaining = channel.health.circuit_open_until - time.monotonic()
                logger.debug(
                    "Channel '%s' circuit breaker open (%.1fs remaining), re-queuing",
                    msg.channel,
                    remaining,
                )
                self._outbound_seq += 1
                self._outbound.put_nowait((msg.priority, self._outbound_seq, msg))
                await asyncio.sleep(min(remaining, 1.0))
                continue

            msg = downgrade_components(msg, channel)
            msg = _apply_outbound_risk_gate(msg)

            limiter = self._limiters.get(msg.channel)
            if limiter:
                await limiter.acquire()

            rate_limit = channel.capabilities.send_rate_limit
            if rate_limit > 0:
                last_send = self._last_send_times.get(msg.channel, 0.0)
                elapsed = time.monotonic() - last_send
                if elapsed < rate_limit:
                    await asyncio.sleep(rate_limit - elapsed)

            t0 = time.monotonic()
            try:
                if await self._try_cp_egress(msg):
                    latency_ms = (time.monotonic() - t0) * 1000
                    channel.activity.record_outbound(latency_ms=latency_ms)
                    channel.health.record_success()
                    if rate_limit > 0:
                        self._last_send_times[msg.channel] = time.monotonic()
                    continue

                await send_with_retry(
                    channel.send,
                    msg,
                    config=channel.retry_config,
                    should_retry=channel.should_retry,
                    extract_retry_after=channel.extract_retry_after,
                    label=f"send:{msg.channel}",
                )
                latency_ms = (time.monotonic() - t0) * 1000
                channel.activity.record_outbound(latency_ms=latency_ms)
                channel.health.record_success()
                if rate_limit > 0:
                    self._last_send_times[msg.channel] = time.monotonic()
            except Exception as e:
                channel.activity.record_error()
                channel.health.record_failure(str(e))
                logger.warning("Channel '%s' send failed after retries: %s", msg.channel, e)
                await self._record_outbound_failure(msg, str(e), retries_exhausted=False)
