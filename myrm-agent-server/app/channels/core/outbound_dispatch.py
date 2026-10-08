"""Outbound delivery pipeline for MessageBus: priority dispatch loop and direct send.

[INPUT]
- channels.core.outbound_prepare::apply_correlation_context, apply_outbound_risk_gate, downgrade_components
- channels.core.outbound_failure::OutboundFailureMixin (POS: DLQ persistence and permanent-failure notification)
- channels.core.outbound_gate::get_outbound_content_gate (POS: pre-publish content and link liveness gate)
- channels.reliability.retry::send_with_retry (POS: async retry utility with exponential backoff)
- services.channels.cp_egress_client (POS: sandbox-to-control-plane outbound bridge)

[OUTPUT]
- OutboundDispatchMixin: _dispatch_loop (priority dispatch), send_tracked (direct send returning message_id),
  control-plane egress routing and durable outbound recovery

[POS]
Delivery half of MessageBus. The host owns queues, channel registry and limiters; the mixin only drives them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.channels.core.outbound_failure import OutboundFailureMixin
from app.channels.core.outbound_gate import get_outbound_content_gate
from app.channels.core.outbound_prepare import (
    apply_correlation_context,
    apply_outbound_risk_gate,
    downgrade_components,
    get_correlation_context,
)
from app.channels.reliability.rate_limiter import TokenBucket
from app.channels.reliability.retry import send_with_retry
from app.channels.types import ChannelStatus, OutboundMessage

logger = logging.getLogger(__name__)


def _record_data_plane_outbound(msg: OutboundMessage) -> None:
    """Fire-and-forget: persist outbound agent message to the channel data plane."""
    try:
        from app.channels.routing.channel_data_plane import ChannelDataPlaneService

        asyncio.create_task(
            ChannelDataPlaneService.record_outbound(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=msg.content,
                thread_id=msg.thread_id,
                reply_to_id=msg.reply_to_id,
            )
        )
    except Exception as exc:
        logger.debug("Failed to schedule data plane outbound recording: %s", exc)


class OutboundDispatchMixin(OutboundFailureMixin):
    """Priority dispatch loop and direct send for the outbound path."""

    _max_queue_size: int
    _outbound: asyncio.PriorityQueue[tuple[int, int, OutboundMessage]] | None
    _outbound_seq: int
    _limiters: dict[str, TokenBucket]
    _last_send_times: dict[str, float]
    _running: bool

    if TYPE_CHECKING:

        def _ensure_queues(self) -> None: ...

    async def send_tracked(self, msg: OutboundMessage) -> str | None:
        """Send a message directly (bypassing the queue) and return its platform message_id.

        Used for messages that need lifecycle management (e.g. approval prompts
        that will be edited after the user responds). Applies the same retry
        policy as the dispatch loop for reliability.
        """
        msg = apply_correlation_context(msg)
        channel = self._channels.get(msg.channel)
        if not channel:
            logger.warning("No channel registered for '%s', cannot send_tracked", msg.channel)
            return None
        if channel.status == ChannelStatus.DISABLED:
            logger.debug("Channel '%s' is disabled, cannot send_tracked", msg.channel)
            return None
        if channel.status == ChannelStatus.STOPPED:
            logger.debug("Channel '%s' is stopped, cannot send_tracked", msg.channel)
            return None
        msg = downgrade_components(msg, channel)
        msg = apply_outbound_risk_gate(msg)
        msg = await self._durable_outbound.persist_direct_send(msg)

        rate_limit = channel.capabilities.send_rate_limit
        if rate_limit > 0:
            last_send = self._last_send_times.get(msg.channel, 0.0)
            elapsed = time.monotonic() - last_send
            if elapsed < rate_limit:
                await asyncio.sleep(rate_limit - elapsed)

        t0 = time.monotonic()
        try:
            await self._durable_outbound.mark_attempting(msg)
            if await self._try_cp_egress(msg):
                await self._durable_outbound.ack(msg)
                latency_ms = (time.monotonic() - t0) * 1000
                channel.activity.record_outbound(latency_ms=latency_ms)
                _record_data_plane_outbound(msg)
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
            if result is None:
                await self._record_outbound_failure(
                    msg,
                    "channel send returned no message_id",
                    retries_exhausted=True,
                )
                return None
            await self._durable_outbound.ack(msg)
            latency_ms = (time.monotonic() - t0) * 1000
            channel.activity.record_outbound(latency_ms=latency_ms)
            _record_data_plane_outbound(msg)
            if rate_limit > 0:
                self._last_send_times[msg.channel] = time.monotonic()
            return result
        except Exception as e:
            channel.activity.record_error()
            logger.warning("Channel '%s' send_tracked failed after retries: %s", msg.channel, e)
            await self._record_outbound_failure(msg, str(e), retries_exhausted=True)
            return None

    async def _try_cp_egress(self, msg: OutboundMessage) -> bool:
        """Route outbound via Control Plane when running in SaaS sandbox."""
        from app.services.channels.cp_egress_client import (
            send_via_control_plane,
            should_route_via_control_plane,
        )

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

    async def _maybe_recover_durable_outbound(self) -> None:
        """Re-inject disk-pending deliveries when the in-memory queue has capacity."""
        if not self._durable_outbound.is_enabled() or self._outbound is None:
            return
        if self._outbound.qsize() >= self._max_queue_size:
            return
        await self._durable_outbound.recover_into_bus(self)

    async def _dispatch_loop(self) -> None:
        """Continuously dequeue outbound messages and route to channels (priority order)."""
        self._ensure_queues()
        assert self._outbound is not None
        while self._running:
            try:
                _priority, _seq, msg = await asyncio.wait_for(self._outbound.get(), timeout=1.0)
            except TimeoutError:
                await self._maybe_recover_durable_outbound()
                continue
            except asyncio.CancelledError:
                break

            channel = self._channels.get(msg.channel)
            if not channel:
                if await self._try_cp_egress(msg):
                    await self._durable_outbound.ack(msg)
                    continue
                logger.warning(
                    "No channel registered for '%s', retaining durable outbound obligation",
                    msg.channel,
                )
                self._durable_outbound.release_inflight(msg)
                continue
            if channel.status in (ChannelStatus.DISABLED, ChannelStatus.STOPPED):
                logger.debug(
                    "Channel '%s' is %s, retaining durable outbound obligation",
                    msg.channel,
                    channel.status.value,
                )
                self._durable_outbound.release_inflight(msg)
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
            msg = apply_outbound_risk_gate(msg)

            # Pre-Publish Outbound Content & Link Liveness Gate
            gate_result = await get_outbound_content_gate().evaluate_and_apply(msg)
            if gate_result is None:
                # Fail-Closed HOLD triggered on dead links for unattended cron/broadcast messages
                logger.warning(
                    "Outbound message held by pre-publish content gate for channel '%s'",
                    msg.channel,
                )
                await self._durable_outbound.ack(msg)
                continue
            msg = gate_result

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
                await self._durable_outbound.mark_attempting(msg)
                if await self._try_cp_egress(msg):
                    await self._durable_outbound.ack(msg)
                    latency_ms = (time.monotonic() - t0) * 1000
                    channel.activity.record_outbound(latency_ms=latency_ms)
                    channel.health.record_success()
                    _record_data_plane_outbound(msg)
                    if rate_limit > 0:
                        self._last_send_times[msg.channel] = time.monotonic()
                    continue

                send_result = await send_with_retry(
                    channel.send,
                    msg,
                    config=channel.retry_config,
                    should_retry=channel.should_retry,
                    extract_retry_after=channel.extract_retry_after,
                    label=f"send:{msg.channel}",
                )
                if send_result is None:
                    await self._record_outbound_failure(
                        msg,
                        "channel send returned no message_id",
                        retries_exhausted=True,
                    )
                    continue
                await self._durable_outbound.ack(msg)
                latency_ms = (time.monotonic() - t0) * 1000
                channel.activity.record_outbound(latency_ms=latency_ms)
                channel.health.record_success()
                _record_data_plane_outbound(msg)
                if rate_limit > 0:
                    self._last_send_times[msg.channel] = time.monotonic()
            except Exception as e:
                channel.activity.record_error()
                channel.health.record_failure(str(e))
                logger.warning("Channel '%s' send failed after retries: %s", msg.channel, e)
                await self._record_outbound_failure(msg, str(e), retries_exhausted=False)
