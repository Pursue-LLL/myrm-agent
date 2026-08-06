"""Durable outbound gate — disk persistence before IM channel sends.

Bridges MessageBus in-memory outbound queue with harness delivery storage so
process crashes between agent completion and platform delivery do not silently
drop final replies. Web/chat channels are excluded (SSE already durable).

[INPUT]
- myrm_agent_harness.infra.delivery.storage (POS: Delivery queue storage layer. Atomic writes; pending/attempting phase lifecycle.)
- channels.types::OutboundMessage (POS: outbound payload)
- channels.i18n::channel_t (POS: recovery marker i18n)

[OUTPUT]
- DurableOutboundGate: persist / mark_attempting / ack / recover / count_pending / track_enqueued / release_inflight
- METADATA_DELIVERY_ID: internal metadata key for delivery correlation

[POS]
Server-layer reliability adapter. Keeps harness storage generic; wires business
MessageBus to disk-backed outbound obligation without a second queue subsystem.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.delivery.storage import (
    QueuedDelivery,
    ack_delivery,
    generate_delivery_id,
    load_pending_deliveries,
    save_delivery,
)

from app.channels.i18n import channel_t, get_locale_from_metadata
from app.channels.types import OutboundMessage

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus

logger = logging.getLogger(__name__)

METADATA_DELIVERY_ID = "_durable_delivery_id"
METADATA_RECOVERED = "_durable_recovered"

_SKIP_CHANNELS = frozenset({"web", "chat", "silent"})


class DurableOutboundGate:
    """Disk-backed outbound obligation gate for IM channels."""

    def __init__(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self._inflight_ids: set[str] = set()

    @property
    def base_dir(self) -> Path | None:
        return self._base_dir

    def is_enabled(self) -> bool:
        return self._base_dir is not None

    @staticmethod
    def is_durable_channel(channel: str) -> bool:
        return channel not in _SKIP_CHANNELS

    @staticmethod
    def get_delivery_id(msg: OutboundMessage) -> str | None:
        meta = msg.metadata
        if not isinstance(meta, dict):
            return None
        raw = meta.get(METADATA_DELIVERY_ID)
        return str(raw) if raw else None

    @staticmethod
    def is_recovered(msg: OutboundMessage) -> bool:
        meta = msg.metadata
        return isinstance(meta, dict) and bool(meta.get(METADATA_RECOVERED))

    async def prepare_enqueue(self, msg: OutboundMessage) -> OutboundMessage:
        """Persist outbound obligation before in-memory enqueue."""
        if not self.is_enabled() or not self.is_durable_channel(msg.channel):
            return msg
        if self.is_recovered(msg):
            return msg

        existing_id = self.get_delivery_id(msg)
        delivery_id = existing_id or generate_delivery_id(msg.channel, msg.recipient_id)

        delivery = QueuedDelivery(
            id=delivery_id,
            channel=msg.channel,
            recipient=msg.recipient_id,
            content=msg.to_dict(),
            enqueued_at=time.time(),
            priority=msg.priority.value,
            phase="pending",
        )
        await save_delivery(delivery, base_dir=self._base_dir)

        meta = dict(msg.metadata) if isinstance(msg.metadata, dict) else {}
        meta[METADATA_DELIVERY_ID] = delivery_id
        return dataclasses.replace(msg, metadata=meta)

    def track_enqueued(self, msg: OutboundMessage) -> None:
        """Mark delivery as present in the in-memory outbound queue."""
        delivery_id = self.get_delivery_id(msg)
        if delivery_id:
            self._inflight_ids.add(delivery_id)

    def release_inflight(self, msg: OutboundMessage) -> None:
        """Release in-memory tracking so disk recovery can retry."""
        delivery_id = self.get_delivery_id(msg)
        if delivery_id:
            self._inflight_ids.discard(delivery_id)

    async def persist_direct_send(self, msg: OutboundMessage) -> OutboundMessage:
        """Persist before a direct send path (send_tracked / cron / edit)."""
        return await self.prepare_enqueue(msg)

    async def mark_attempting(self, msg: OutboundMessage) -> None:
        """Mark delivery as in-flight before platform API call."""
        if not self.is_enabled() or not self.is_durable_channel(msg.channel):
            return

        delivery_id = self.get_delivery_id(msg)
        if not delivery_id:
            return

        pending = await load_pending_deliveries(base_dir=self._base_dir)
        existing = next((item for item in pending if item.id == delivery_id), None)
        enqueued_at = existing.enqueued_at if existing is not None else time.time()

        delivery = QueuedDelivery(
            id=delivery_id,
            channel=msg.channel,
            recipient=msg.recipient_id,
            content=msg.to_dict(),
            enqueued_at=enqueued_at,
            priority=msg.priority.value,
            phase="attempting",
        )
        await save_delivery(delivery, base_dir=self._base_dir)

    async def ack(self, msg: OutboundMessage) -> None:
        """Remove persisted obligation after successful delivery."""
        if not self.is_enabled():
            return

        delivery_id = self.get_delivery_id(msg)
        if not delivery_id:
            return

        await ack_delivery(delivery_id, base_dir=self._base_dir)
        self._inflight_ids.discard(delivery_id)

    async def count_pending(self) -> int:
        """Return count of disk-persisted pending outbound deliveries."""
        if not self.is_enabled():
            return 0
        pending = await load_pending_deliveries(base_dir=self._base_dir)
        return len(pending)

    async def recover_into_bus(self, bus: MessageBus) -> int:
        """Re-inject disk-pending deliveries into the in-memory outbound queue."""
        if not self.is_enabled():
            return 0

        pending = [
            item
            for item in await load_pending_deliveries(base_dir=self._base_dir)
            if item.id not in self._inflight_ids
        ]
        if not pending:
            return 0

        recovered = 0
        for delivery in pending:
            if not self.is_durable_channel(delivery.channel):
                await ack_delivery(delivery.id, base_dir=self._base_dir)
                continue

            msg = self._delivery_to_outbound(delivery)
            await save_delivery(
                replace(delivery, phase="pending"),
                base_dir=self._base_dir,
            )
            await bus.publish_outbound(msg, _skip_durable_persist=True)
            recovered += 1

        if recovered:
            logger.info("Recovered %d durable outbound deliveries after restart", recovered)
        return recovered

    def _delivery_to_outbound(self, delivery: QueuedDelivery) -> OutboundMessage:
        msg = OutboundMessage.from_dict(delivery.content)
        meta = dict(msg.metadata) if isinstance(msg.metadata, dict) else {}
        meta[METADATA_DELIVERY_ID] = delivery.id
        meta[METADATA_RECOVERED] = True

        if delivery.phase == "attempting":
            locale = get_locale_from_metadata(meta)
            marker = channel_t(locale, "durable_outbound_recovered")
            msg = dataclasses.replace(msg, content=f"{marker}\n\n{msg.content}")

        return dataclasses.replace(msg, metadata=meta)
