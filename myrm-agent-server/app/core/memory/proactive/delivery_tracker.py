"""Follow-up delivery tracking for heartbeat runs.

[INPUT]
- myrm_agent_harness.toolkits.memory.proactive.types::CommitmentStatus
- app.core.memory.proactive.sqlite_store::SqlAlchemyCommitmentStore

[OUTPUT]
- begin_follow_up_delivery / register_follow_up_attempts / confirm_follow_up_delivery

[POS]
ContextVar-based tracker that registers commitment IDs injected into a
situation report and confirms delivery after the agent responds.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar

from myrm_agent_harness.toolkits.memory.proactive.types import CommitmentStatus

logger = logging.getLogger(__name__)

_follow_up_attempt_ids: ContextVar[list[str]] = ContextVar("_follow_up_attempt_ids", default=[])


def begin_follow_up_delivery() -> None:
    """Reset the delivery tracker for a new heartbeat run."""
    _follow_up_attempt_ids.set([])


def register_follow_up_attempts(ids: list[str]) -> None:
    """Record commitment IDs included in the current situation report."""
    if ids:
        _follow_up_attempt_ids.set(list(ids))


def get_follow_up_attempt_ids() -> list[str]:
    """Return commitment IDs awaiting delivery confirmation."""
    return list(_follow_up_attempt_ids.get())


def reset_follow_up_delivery() -> None:
    """Clear pending delivery IDs without marking sent."""
    _follow_up_attempt_ids.set([])


async def confirm_follow_up_delivery(*, delivered: bool) -> None:
    """Mark injected follow-ups as sent when delivery succeeded."""
    ids = get_follow_up_attempt_ids()
    reset_follow_up_delivery()
    if not ids or not delivered:
        return

    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    store = SqlAlchemyCommitmentStore()
    now_ms = int(time.time() * 1000)
    try:
        await store.mark_status(ids, CommitmentStatus.SENT, now_ms)
    except Exception:
        logger.warning("Failed to confirm delivery for %d follow-ups", len(ids), exc_info=True)
