"""Outbound failure handling: DLQ persistence and permanent-failure notification.

[INPUT]
- myrm_agent_harness.infra.delivery (POS: dead-letter queue, notification ledger and delivery storage)
- channels.reliability.durable_outbound::DurableOutboundGate (POS: disk-backed outbound obligation)
- channels.types::OutboundMessage (POS: outbound payload)

[OUTPUT]
- OutboundFailureMixin: _record_outbound_failure (shared DLQ + permanent-failure callback for sync and async
  send paths), DLQ re-enqueue callback, DLQ threshold alert and notification dedup

[POS]
Failure half of MessageBus. The host owns the state declared on the mixin; the mixin never creates it.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.delivery.dead_letter import DeadLetterQueue
from myrm_agent_harness.infra.delivery.notification_ledger import (
    PermanentFailureNotificationLedger,
)
from myrm_agent_harness.infra.delivery.storage import QueuedDelivery, move_to_failed

from app.channels.core.base import BaseChannel
from app.channels.core.events import EventEmitter
from app.channels.reliability.durable_outbound import DurableOutboundGate
from app.channels.types import OutboundMessage

logger = logging.getLogger(__name__)

_DEFAULT_DLQ_ALERT_THRESHOLD = 100


class OutboundFailureMixin:
    """DLQ persistence and permanent-failure notification for failed outbound sends."""

    _channels: dict[str, BaseChannel]
    _dlq: DeadLetterQueue | None
    _dlq_dir: Path | None
    _dlq_alert_cooldown_sec: int
    _last_dlq_alert_times: dict[str, float]
    _notification_ledger: PermanentFailureNotificationLedger | None
    _presync_notified_delivery_ids: set[str]
    _durable_outbound: DurableOutboundGate
    on_permanent_failure: Callable[[QueuedDelivery, str], Awaitable[None]] | None
    events: EventEmitter

    if TYPE_CHECKING:

        async def publish_outbound(self, msg: OutboundMessage, *, _skip_durable_persist: bool = False) -> None: ...

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
        await self._durable_outbound.ack(msg)

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
