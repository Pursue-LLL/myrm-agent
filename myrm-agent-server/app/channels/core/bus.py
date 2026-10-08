"""Async message bus for channel routing.

Decouples message producers (Cron executor, Agent runtime) from
consumers (Channel providers). Uses ``asyncio.PriorityQueue`` for
priority-based dispatch with back-pressure.


[INPUT]
- channels.core.outbound_dispatch::OutboundDispatchMixin (POS: priority dispatch loop and direct-send pipeline)
- channels.core.outbound_prepare::apply_correlation_context, get_correlation_context (POS: correlation lineage)
- channels.core.base::BaseChannel (POS: channel abstract base class)
- channels.reliability.durable_outbound::DurableOutboundGate (POS: disk-backed outbound obligation)
- channels.reliability.rate_limiter::create_limiter (POS: per-channel rate limiter)

[OUTPUT]
- MessageBus: async message bus managing outbound/inbound queues, channel registration and DLQ admin
- MessageBus.publish_outbound(): enqueues with DurableOutboundGate disk persist (IM channels)
- MessageBus.edit_channel_message(): edits a sent message (for updating approval status)
- create_default_message_bus: convenience factory with DLQ support

[POS]
Message routing hub and state holder. Producers call publish_outbound; the dispatch loop (mixin) routes
by priority to the target channel (SYSTEM > NORMAL > BULK). Inbound messages enter the _inbound
queue via channel _emit_inbound callbacks, consumed by AgentRouter.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from myrm_agent_harness.infra.delivery.dead_letter import DeadLetterQueue
from myrm_agent_harness.infra.delivery.notification_ledger import (
    PermanentFailureNotificationLedger,
)
from myrm_agent_harness.infra.delivery.storage import (
    QueuedDelivery,
    delete_failed_delivery,
)

from app.channels.core.base import BaseChannel
from app.channels.core.events import EventEmitter
from app.channels.core.outbound_dispatch import OutboundDispatchMixin
from app.channels.core.outbound_prepare import apply_correlation_context, get_correlation_context
from app.channels.reliability.durable_outbound import DurableOutboundGate
from app.channels.reliability.rate_limiter import create_limiter
from app.channels.types import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE_SIZE = 256


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


class MessageBus(OutboundDispatchMixin):
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
        self._outbound = None
        self._outbound_seq = 0
        self._inbound: asyncio.Queue[InboundMessage] | None = None
        self._channels = {}
        self._limiters = {}
        self._last_send_times = {}
        self._dispatch_task: asyncio.Task[None] | None = None
        self._running = False
        self._dlq_dir = dlq_dir
        self._dlq = None
        self.events = EventEmitter("MessageBus")
        self._dlq_alert_cooldown_sec = dlq_alert_cooldown_sec
        self._last_dlq_alert_times = {}
        self.on_permanent_failure = on_permanent_failure
        self._notification_ledger = notification_ledger
        self._presync_notified_delivery_ids = set()
        self._durable_outbound = DurableOutboundGate(dlq_dir)

    @property
    def durable_outbound(self) -> DurableOutboundGate:
        return self._durable_outbound

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

    async def publish_outbound(
        self,
        msg: OutboundMessage,
        *,
        _skip_durable_persist: bool = False,
    ) -> None:
        """Enqueue an outbound message for priority-based delivery."""
        self._ensure_queues()
        assert self._outbound is not None
        msg = apply_correlation_context(msg)
        if not _skip_durable_persist:
            msg = await self._durable_outbound.prepare_enqueue(msg)
        try:
            self._outbound_seq += 1
            self._outbound.put_nowait((msg.priority, self._outbound_seq, msg))
            self._durable_outbound.track_enqueued(msg)
        except asyncio.QueueFull:
            logger.warning("Outbound queue full, dropping message for channel '%s'", msg.channel)
            self._durable_outbound.release_inflight(msg)

    async def edit_channel_message(self, channel_name: str, chat_id: str, message_id: str, content: str) -> bool:
        """Edit a previously sent message on a channel. Returns True if successful."""
        from app.services.channels.cp_egress_client import (
            send_via_control_plane,
            should_route_via_control_plane,
        )

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
            await self._durable_outbound.recover_into_bus(self)
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
