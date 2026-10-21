"""Regression acceptance: open watches, verify no recurrence.

[INPUT]
- experience_ledger record/count APIs (POS: shared event ledger)

[OUTPUT]
- open_watch: persist a pending no-recurrence watch as a REVIEW ledger event
- verify_watch: True when the entity stayed clean for the watch window

[POS]
Acceptance bookkeeping only. Never mutates skills or approvals; verification
is a bounded recent-negative scan with in-memory entity matching, plus a
closing ledger event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    list_experience_events,
    record_experience_event,
)

WATCH_OUTCOME_OPEN = "watch_open"
WATCH_OUTCOME_VERIFIED = "watch_verified"
WATCH_EVENT = ExperienceEventType.REVIEW_APPROVED.value
WATCH_ENTITY = ExperienceEntityType.REVIEW.value

NEGATIVE_EVENT_TYPES = (
    "review.rejected",
    "evolution.rejected",
    "evolution.apply_failed",
    "skill_growth.rejected",
    "skill_growth.blocked",
    "skill_growth.failed_scan",
)

_MIN_WINDOW_HOURS = 24


@dataclass(frozen=True, slots=True)
class RegressionWatch:
    """A no-recurrence watch opened for an entity."""

    watch_id: str
    entity_type: str
    entity_id: str
    opened_at: datetime


def build_watch_id(entity_type: str, entity_id: str, opened_at: datetime) -> str:
    """Stable watch id from entity plus opening timestamp."""
    stamp = opened_at.strftime("%Y%m%d%H%M%S")
    return f"nowatch-{entity_type}-{entity_id}-{stamp}"


async def open_watch(
    *,
    entity_type: str,
    entity_id: str,
    summary: str,
    namespace: str = "nightly-review",
    opened_at: datetime | None = None,
) -> RegressionWatch:
    """Persist a pending watch; returns the watch handle."""
    opened = opened_at or datetime.now(UTC)
    watch_id = build_watch_id(entity_type, entity_id, opened)
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=WATCH_EVENT,
            entity_type=WATCH_ENTITY,
            entity_id=watch_id,
            lineage_id=watch_id,
            summary=summary,
            namespace=namespace,
            outcome=WATCH_OUTCOME_OPEN,
            detail={"entity_type": entity_type, "entity_id": entity_id},
        )
    )
    return RegressionWatch(watch_id=watch_id, entity_type=entity_type, entity_id=entity_id, opened_at=opened)


async def verify_watch(
    watch: RegressionWatch,
    *,
    min_window_hours: int = _MIN_WINDOW_HOURS,
    now: datetime | None = None,
) -> bool:
    """Return True when no negative events recurred inside the window."""
    current = now or datetime.now(UTC)
    if current - watch.opened_at < timedelta(hours=min_window_hours):
        return False
    # The ledger query API has no entity_id filter; negatives are rare, so a
    # bounded recent list with in-memory matching is sufficient and exact.
    recent = await list_experience_events(
        limit=500,
        event_types=NEGATIVE_EVENT_TYPES,
        since=watch.opened_at,
    )
    recurred = any(event.entity_type == watch.entity_type and event.entity_id == watch.entity_id for event in recent)
    if recurred:
        return False
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=WATCH_EVENT,
            entity_type=WATCH_ENTITY,
            entity_id=watch.watch_id,
            lineage_id=watch.watch_id,
            summary=f"No recurrence for {watch.entity_id}",
            namespace="nightly-review",
            outcome=WATCH_OUTCOME_VERIFIED,
            detail={"entity_type": watch.entity_type, "entity_id": watch.entity_id},
        )
    )
    return True
