"""Outbound delivery pipeline for MessageBus: priority dispatch loop and direct send.

[INPUT]
- channels.core.outbound_prepare::apply_correlation_context, prepare_outbound, delivery_unconfirmed, undelivered_part,
  partial_failure_note (POS: shared preparation and delivery verdicts)
- channels.core.outbound_failure::OutboundFailureMixin (POS: DLQ persistence and permanent-failure notification)
- channels.core.outbound_gate::get_outbound_content_gate (POS: pre-publish link liveness gate)
- channels.core.outbound_media::discard_ephemeral_media (POS: temp attachment cleanup once delivery is final)
- channels.reliability.retry::send_with_retry (POS: async retry utility with exponential backoff)
- services.channels.cp_egress_client (POS: sandbox-to-control-plane outbound bridge)

[OUTPUT]
- OutboundDispatchMixin: _dispatch_loop (queued delivery), send_now (strict direct send that raises on failure),
  send_tracked (lenient wrapper returning the message id), control-plane egress routing, durable outbound recovery

[POS]
Delivery half of MessageBus. The host owns queues, channel registry and limiters; the mixin only drives them.
Queued and direct sends share one route resolution, one preparation step and one settle step, so a message
is acknowledged only when the channel proved delivery and a failure is always recorded exactly once.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from typing import TYPE_CHECKING

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError, DeliveryUnconfirmedError
from app.channels.core.outbound_failure import OutboundFailureMixin
from app.channels.core.outbound_gate import get_outbound_content_gate
from app.channels.core.outbound_media import discard_ephemeral_media
from app.channels.core.outbound_prepare import (
    apply_correlation_context,
    delivery_unconfirmed,
    get_correlation_context,
    partial_failure_note,
    prepare_outbound,
    undelivered_part,
)
from app.channels.reliability.rate_limiter import TokenBucket
from app.channels.reliability.retry import send_with_retry
from app.channels.types import ChannelCapabilities, ChannelStatus, OutboundMessage

logger = logging.getLogger(__name__)

# Control-plane egress carries plain text only, so it prepares messages with the most limited capabilities.
_TEXT_ONLY = ChannelCapabilities()


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


def _is_partial_delivery(exc: Exception) -> bool:
    """The platform already accepted part of the message, so the channel itself is healthy."""
    return isinstance(exc, ChannelSendError) and exc.accepted


@dataclasses.dataclass(frozen=True, slots=True)
class _Route:
    """Where one outbound message goes.

    ``channel`` is the local provider; ``None`` means control-plane egress (cloud sandbox, text only).
    ``unavailable`` holds the reason when the target cannot take messages right now.
    """

    channel: BaseChannel | None
    unavailable: str | None = None

    @property
    def capabilities(self) -> ChannelCapabilities:
        return self.channel.capabilities if self.channel is not None else _TEXT_ONLY


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

    async def send_now(self, msg: OutboundMessage) -> str | None:
        """Deliver ``msg`` immediately (bypassing the queue); raise unless the recipient provably got it.

        Returns the platform message id, or ``None`` on channels that do not report ids. A failure is
        settled like a queued send (durable obligation released, DLQ entry, permanent-failure callback)
        and then raised, so callers that must know the outcome (cron, notify) can act on it.
        """
        origin = apply_correlation_context(msg)
        route = self._resolve_route(origin)
        if route.unavailable:
            discard_ephemeral_media(origin.media)
            raise ChannelSendError(route.unavailable, channel=origin.channel, retriable=False)
        msg = prepare_outbound(origin, route.capabilities, channel_name=origin.channel)
        msg = await self._durable_outbound.persist_direct_send(msg)
        await self._pace(msg.channel, route.capabilities.send_rate_limit)
        return await self._deliver(msg, origin, route, label=f"send_now:{msg.channel}", final_on_error=True)

    async def send_tracked(self, msg: OutboundMessage) -> str | None:
        """``send_now`` for callers that only need the platform message id (e.g. to edit the message later).

        Returns ``None`` when the send failed (already logged and recorded) or the channel reports no ids.
        """
        try:
            return await self.send_now(msg)
        except Exception as exc:
            logger.debug("send_tracked on '%s' did not deliver: %s", msg.channel, exc)
            return None

    def _resolve_route(self, msg: OutboundMessage) -> _Route:
        """Pick the delivery target; control-plane routing wins over any locally registered provider."""
        from app.services.channels.cp_egress_client import should_route_via_control_plane

        meta = msg.metadata if isinstance(msg.metadata, dict) else None
        if should_route_via_control_plane(msg.channel, meta):
            return _Route(channel=None)
        channel = self._channels.get(msg.channel)
        if channel is None:
            return _Route(channel=None, unavailable=f"No channel registered for '{msg.channel}'")
        if channel.status in (ChannelStatus.DISABLED, ChannelStatus.STOPPED):
            return _Route(channel=channel, unavailable=f"Channel '{msg.channel}' is {channel.status.value}")
        return _Route(channel=channel)

    async def _pace(self, channel_name: str, rate_limit: float) -> None:
        """Honor the channel's minimum interval between sends."""
        if rate_limit <= 0:
            return
        elapsed = time.monotonic() - self._last_send_times.get(channel_name, 0.0)
        if elapsed < rate_limit:
            await asyncio.sleep(rate_limit - elapsed)

    async def _deliver(
        self,
        msg: OutboundMessage,
        origin: OutboundMessage,
        route: _Route,
        *,
        label: str,
        final_on_error: bool,
    ) -> str | None:
        """Attempt delivery (provider retries included) and settle the outcome exactly once.

        ``msg`` is the prepared message that goes out; ``origin`` is what the producer handed over, so
        ephemeral files that preparation dropped (unsupported attachments) are still released.
        Success releases the durable obligation and updates activity. Failure is recorded (DLQ,
        permanent-failure callback) and re-raised; ``final_on_error`` marks it as not worth a DLQ retry.
        """
        t0 = time.monotonic()
        try:
            await self._durable_outbound.mark_attempting(msg)
            message_id = await self._attempt_send(msg, route, label=label)
        except Exception as exc:
            await self._settle_failure(msg, origin, route, exc, final_on_error=final_on_error)
            raise
        await self._durable_outbound.ack(msg)
        discard_ephemeral_media(origin.media)
        if route.channel is not None:
            route.channel.activity.record_outbound(latency_ms=(time.monotonic() - t0) * 1000)
        _record_data_plane_outbound(msg)
        if route.capabilities.send_rate_limit > 0:
            self._last_send_times[msg.channel] = time.monotonic()
        return message_id

    async def _attempt_send(self, msg: OutboundMessage, route: _Route, *, label: str) -> str | None:
        """One delivery through the route; raises when delivery is not proven."""
        channel = route.channel
        if channel is None:
            return await self._send_via_control_plane(msg)
        result = await send_with_retry(
            channel.send,
            msg,
            config=channel.retry_config,
            should_retry=channel.should_retry,
            extract_retry_after=channel.extract_retry_after,
            label=label,
        )
        if delivery_unconfirmed(channel.capabilities, msg, result):
            raise DeliveryUnconfirmedError(channel=msg.channel)
        return result

    async def _send_via_control_plane(self, msg: OutboundMessage) -> str:
        """Deliver through the Control Plane egress (cloud sandbox); text content only."""
        from app.services.channels.cp_egress_client import send_via_control_plane

        meta = msg.metadata if isinstance(msg.metadata, dict) else {}
        ctx = msg.correlation_context or get_correlation_context()
        tenant_id = ctx.user_id if ctx and ctx.user_id else (msg.user_id or "")
        update_id = str(meta["update_message_id"]) if meta.get("update_message_id") else None

        message_id = await send_via_control_plane(
            channel=msg.channel,
            chat_id=msg.recipient_id,
            content=msg.content,
            tenant_id=tenant_id,
            reply_to_message_id=msg.reply_to_id,
            update_message_id=update_id,
            thread_id=msg.thread_id,
        )
        if message_id is None:
            raise ChannelSendError("control-plane egress failed", channel=msg.channel)
        return message_id

    async def _settle_failure(
        self,
        msg: OutboundMessage,
        origin: OutboundMessage,
        route: _Route,
        exc: Exception,
        *,
        final_on_error: bool,
    ) -> None:
        """Record a failed delivery once; a partial delivery is reported per attachment, never replayed whole.

        Ephemeral files stay only while a failure record may still re-send them.
        """
        if route.channel is not None:
            route.channel.activity.record_error()
        logger.warning("Channel '%s' send failed: %s", msg.channel, exc)

        if isinstance(exc, ChannelSendError) and exc.accepted and msg.media:
            names = exc.failed_attachments or tuple(m.display_name for m in msg.media)
            remainder = undelivered_part(msg, names)
            await self._record_outbound_failure(remainder, str(exc), retries_exhausted=True)
            await self.publish_outbound(partial_failure_note(msg, names))
            discard_ephemeral_media(origin.media, keep_paths={m.path for m in remainder.media})
            return
        final = final_on_error or _is_partial_delivery(exc) or isinstance(exc, DeliveryUnconfirmedError)
        await self._record_outbound_failure(msg, str(exc), retries_exhausted=final)
        discard_ephemeral_media(origin.media, keep_paths={m.path for m in msg.media})

    def _release_unqueued(self, msg: OutboundMessage) -> None:
        """``msg`` leaves memory undelivered: a disk record takes over, otherwise its temp files are freed."""
        self._durable_outbound.release_inflight(msg)
        if not self._durable_outbound.retains(msg):
            discard_ephemeral_media(msg.media)

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

            origin = msg
            route = self._resolve_route(origin)
            channel = route.channel
            if route.unavailable:
                logger.log(
                    logging.DEBUG if channel else logging.WARNING,
                    "%s, retaining durable outbound obligation",
                    route.unavailable,
                )
                self._release_unqueued(origin)
                continue

            if channel is not None and channel.health.circuit_open:
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

            msg = prepare_outbound(origin, route.capabilities, channel_name=origin.channel)
            msg = await get_outbound_content_gate().evaluate_and_apply(msg)

            limiter = self._limiters.get(msg.channel)
            if limiter:
                await limiter.acquire()
            await self._pace(msg.channel, route.capabilities.send_rate_limit)

            try:
                await self._deliver(msg, origin, route, label=f"send:{msg.channel}", final_on_error=False)
            except Exception as exc:
                # Already logged and recorded by _deliver; only the channel health bookkeeping is left.
                if channel is not None and not _is_partial_delivery(exc):
                    channel.health.record_failure(str(exc))
            else:
                if channel is not None:
                    channel.health.record_success()
