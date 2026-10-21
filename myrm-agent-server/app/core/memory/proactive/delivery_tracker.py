"""Follow-up delivery tracking for heartbeat runs.

[INPUT]
- myrm_agent_harness.toolkits.memory.proactive.types::CommitmentStatus
- app.core.memory.proactive.sqlite_store::SqlAlchemyCommitmentStore

[OUTPUT]
- begin_follow_up_delivery / register_follow_up_attempts / confirm_follow_up_delivery

[POS]
ContextVar-based tracker that registers commitment IDs injected into a
situation report; marks SENT on successful delivery ack, or snoozes 6h on skip.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar

from myrm_agent_harness.toolkits.memory.proactive.types import CommitmentStatus

logger = logging.getLogger(__name__)

_FAILED_DELIVERY_SNOOZE_MS = 6 * 60 * 60 * 1000
FAILED_DELIVERY_SNOOZE_MS = _FAILED_DELIVERY_SNOOZE_MS

_follow_up_attempt_ids: ContextVar[tuple[str, ...]] = ContextVar("_follow_up_attempt_ids", default=())


def begin_follow_up_delivery() -> None:
    """Reset the delivery tracker for a new heartbeat run."""
    _follow_up_attempt_ids.set(())


def register_follow_up_attempts(ids: list[str]) -> None:
    """Record commitment IDs included in the current situation report."""
    if ids:
        _follow_up_attempt_ids.set(tuple(ids))


def get_follow_up_attempt_ids() -> list[str]:
    """Return commitment IDs awaiting delivery confirmation."""
    return list(_follow_up_attempt_ids.get())


def reset_follow_up_delivery() -> None:
    """Clear pending delivery IDs without marking sent."""
    _follow_up_attempt_ids.set(())


async def confirm_follow_up_delivery(*, delivered: bool) -> None:
    """Mark injected follow-ups as sent, or snooze after a failed delivery ack."""
    ids = get_follow_up_attempt_ids()
    reset_follow_up_delivery()
    if not ids:
        return

    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    store = SqlAlchemyCommitmentStore()
    now_ms = int(time.time() * 1000)
    try:
        if delivered:
            await store.mark_status(ids, CommitmentStatus.SENT, now_ms)
            return

        until_ms = now_ms + _FAILED_DELIVERY_SNOOZE_MS
        for commitment_id in ids:
            snoozed = await store.snooze(commitment_id, until_ms, now_ms)
            if not snoozed:
                logger.warning(
                    "Failed to snooze follow-up %s after undelivered heartbeat ack",
                    commitment_id,
                )
    except Exception:
        logger.warning("Failed to confirm delivery for %d follow-ups", len(ids), exc_info=True)
