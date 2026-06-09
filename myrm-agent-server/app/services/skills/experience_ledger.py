"""Experience ledger service.

Append-only event ledger for high-value learning artifacts such as migration,
evolution, human review outcomes, and unified skill growth lifecycle events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import desc, func, select

from app.database.connection import get_session
from app.database.models import ExperienceLedgerEvent
from app.services.skills.growth_constants import LEDGER_GROWTH_ACTION_TYPES as SKILL_GROWTH_ACTION_TYPES


class ExperienceEntityType(StrEnum):
    MIGRATION = "migration"
    EVOLUTION = "evolution"
    REVIEW = "review"
    SKILL_GROWTH = "skill_growth"


class ExperienceEventType(StrEnum):
    MIGRATION_SUBMITTED = "migration.submitted"
    MIGRATION_APPROVED = "migration.approved"
    MIGRATION_REJECTED = "migration.rejected"
    EVOLUTION_PENDING = "evolution.pending"
    EVOLUTION_APPROVED = "evolution.approved"
    EVOLUTION_REJECTED = "evolution.rejected"
    EVOLUTION_APPLY_FAILED = "evolution.apply_failed"
    REVIEW_APPROVED = "review.approved"
    REVIEW_REJECTED = "review.rejected"
    SKILL_GROWTH_REVIEW_REQUIRED = "skill_growth.review_required"
    SKILL_GROWTH_AUTO_APPLIED = "skill_growth.auto_applied"
    SKILL_GROWTH_APPROVED = "skill_growth.approved"
    SKILL_GROWTH_REJECTED = "skill_growth.rejected"
    SKILL_GROWTH_BLOCKED = "skill_growth.blocked"
    SKILL_GROWTH_FAILED_SCAN = "skill_growth.failed_scan"


SKILL_GROWTH_STATUS_MAP: dict[str, str] = {
    ExperienceEventType.SKILL_GROWTH_REVIEW_REQUIRED.value: "PENDING_REVIEW",
    ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED.value: "AUTO_APPLIED",
    ExperienceEventType.SKILL_GROWTH_APPROVED.value: "APPROVED",
    ExperienceEventType.SKILL_GROWTH_REJECTED.value: "REJECTED",
    ExperienceEventType.SKILL_GROWTH_BLOCKED.value: "BLOCKED_LOCKED",
    ExperienceEventType.SKILL_GROWTH_FAILED_SCAN.value: "FAILED_SCAN",
    ExperienceEventType.EVOLUTION_PENDING.value: "PENDING_REVIEW",
    ExperienceEventType.EVOLUTION_APPROVED.value: "APPROVED",
    ExperienceEventType.EVOLUTION_REJECTED.value: "REJECTED",
    ExperienceEventType.EVOLUTION_APPLY_FAILED.value: "APPLY_FAILED",
}

SKILL_GROWTH_EVENT_TYPE_BY_STATUS: dict[str, ExperienceEventType] = {
    "PENDING_REVIEW": ExperienceEventType.SKILL_GROWTH_REVIEW_REQUIRED,
    "AUTO_APPLIED": ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED,
    "APPROVED": ExperienceEventType.SKILL_GROWTH_APPROVED,
    "REJECTED": ExperienceEventType.SKILL_GROWTH_REJECTED,
    "BLOCKED_LOCKED": ExperienceEventType.SKILL_GROWTH_BLOCKED,
    "FAILED_SCAN": ExperienceEventType.SKILL_GROWTH_FAILED_SCAN,
}

SKILL_GROWTH_EVENT_TYPES: tuple[str, ...] = tuple(SKILL_GROWTH_STATUS_MAP.keys())
SKILL_GROWTH_NEGATIVE_EVENT_TYPES: tuple[str, ...] = (
    ExperienceEventType.SKILL_GROWTH_REJECTED.value,
    ExperienceEventType.SKILL_GROWTH_BLOCKED.value,
    ExperienceEventType.SKILL_GROWTH_FAILED_SCAN.value,
    ExperienceEventType.EVOLUTION_REJECTED.value,
    ExperienceEventType.EVOLUTION_APPLY_FAILED.value,
)
SKILL_GROWTH_PENDING_EVENT_TYPES: tuple[str, ...] = (
    ExperienceEventType.SKILL_GROWTH_REVIEW_REQUIRED.value,
    ExperienceEventType.EVOLUTION_PENDING.value,
)
SKILL_GROWTH_POSITIVE_EVENT_TYPES: tuple[str, ...] = (
    ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED.value,
    ExperienceEventType.SKILL_GROWTH_APPROVED.value,
    ExperienceEventType.EVOLUTION_APPROVED.value,
)


@dataclass(slots=True)
class ExperienceLedgerWrite:
    event_type: ExperienceEventType | str
    entity_type: ExperienceEntityType | str
    entity_id: str
    lineage_id: str
    summary: str
    namespace: str = "default"
    outcome: str | None = None
    parent_event_id: str | None = None
    artifact_refs: dict[str, object] = field(default_factory=dict)
    metrics_snapshot: dict[str, object] = field(default_factory=dict)
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class SkillGrowthLedgerSummary:
    total_events: int = 0
    positive_events: int = 0
    negative_events: int = 0
    pending_events: int = 0
    auto_applied: int = 0
    approved: int = 0
    rejected: int = 0
    blocked: int = 0
    failed_scan: int = 0
    apply_failed: int = 0


async def record_experience_event(write: ExperienceLedgerWrite) -> ExperienceLedgerEvent:
    event = ExperienceLedgerEvent(
        id=uuid.uuid4().hex,
        namespace=write.namespace,
        event_type=str(write.event_type),
        entity_type=str(write.entity_type),
        entity_id=write.entity_id,
        lineage_id=write.lineage_id,
        parent_event_id=write.parent_event_id,
        outcome=write.outcome,
        summary=write.summary,
        artifact_refs=write.artifact_refs,
        metrics_snapshot=write.metrics_snapshot,
        detail=write.detail,
    )
    async with get_session() as db:
        db.add(event)
        await db.commit()
        await db.refresh(event)
    return event


def get_skill_growth_event_type(status: str) -> ExperienceEventType | None:
    return SKILL_GROWTH_EVENT_TYPE_BY_STATUS.get(status)


async def record_skill_growth_event(
    *,
    entity_id: str,
    draft_type: str,
    status: str,
    summary: str,
    skill_name: str | None = None,
    artifact_refs: dict[str, object] | None = None,
    metrics_snapshot: dict[str, object] | None = None,
    detail: dict[str, object] | None = None,
) -> ExperienceLedgerEvent | None:
    if draft_type not in SKILL_GROWTH_ACTION_TYPES:
        return None

    event_type = get_skill_growth_event_type(status)
    if event_type is None:
        return None

    merged_artifacts: dict[str, object] = {"draft_type": draft_type}
    if skill_name:
        merged_artifacts["skill_name"] = skill_name
    if artifact_refs:
        merged_artifacts.update(artifact_refs)

    merged_detail: dict[str, object] = {"status": status, "draft_type": draft_type}
    if detail:
        merged_detail.update(detail)

    return await record_experience_event(
        ExperienceLedgerWrite(
            event_type=event_type,
            entity_type=ExperienceEntityType.SKILL_GROWTH,
            entity_id=entity_id,
            lineage_id=f"skill_growth:{entity_id}",
            outcome=status.lower(),
            summary=summary,
            artifact_refs=merged_artifacts,
            metrics_snapshot=metrics_snapshot or {},
            detail=merged_detail,
        )
    )


async def list_experience_events(
    *,
    limit: int,
    event_type: str | None = None,
    entity_type: str | None = None,
    lineage_id: str | None = None,
    event_types: tuple[str, ...] | None = None,
    entity_types: tuple[str, ...] | None = None,
    since: datetime | None = None,
) -> list[ExperienceLedgerEvent]:
    async with get_session() as db:
        stmt = select(ExperienceLedgerEvent)
        if event_type:
            stmt = stmt.where(ExperienceLedgerEvent.event_type == event_type)
        if entity_type:
            stmt = stmt.where(ExperienceLedgerEvent.entity_type == entity_type)
        if lineage_id:
            stmt = stmt.where(ExperienceLedgerEvent.lineage_id == lineage_id)
        if event_types:
            stmt = stmt.where(ExperienceLedgerEvent.event_type.in_(event_types))
        if entity_types:
            stmt = stmt.where(ExperienceLedgerEvent.entity_type.in_(entity_types))
        if since is not None:
            stmt = stmt.where(ExperienceLedgerEvent.created_at >= since)
        stmt = stmt.order_by(desc(ExperienceLedgerEvent.created_at)).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def count_experience_events(
    *,
    event_type: str | None = None,
    entity_type: str | None = None,
    lineage_id: str | None = None,
    event_types: tuple[str, ...] | None = None,
    entity_types: tuple[str, ...] | None = None,
    since: datetime | None = None,
) -> int:
    async with get_session() as db:
        stmt = select(func.count()).select_from(ExperienceLedgerEvent)
        if event_type:
            stmt = stmt.where(ExperienceLedgerEvent.event_type == event_type)
        if entity_type:
            stmt = stmt.where(ExperienceLedgerEvent.entity_type == entity_type)
        if lineage_id:
            stmt = stmt.where(ExperienceLedgerEvent.lineage_id == lineage_id)
        if event_types:
            stmt = stmt.where(ExperienceLedgerEvent.event_type.in_(event_types))
        if entity_types:
            stmt = stmt.where(ExperienceLedgerEvent.entity_type.in_(entity_types))
        if since is not None:
            stmt = stmt.where(ExperienceLedgerEvent.created_at >= since)
        total = await db.scalar(stmt)
        return int(total or 0)


def get_skill_growth_event_status(event_type: str) -> str | None:
    return SKILL_GROWTH_STATUS_MAP.get(event_type)


def get_skill_growth_event_source(entity_type: str) -> str:
    if entity_type == ExperienceEntityType.EVOLUTION.value:
        return "manual_evolution"
    return "background_review"


async def list_skill_growth_events(
    *,
    limit: int = 50,
    days: int | None = None,
    negative_only: bool = False,
) -> list[ExperienceLedgerEvent]:
    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    event_types = SKILL_GROWTH_NEGATIVE_EVENT_TYPES if negative_only else SKILL_GROWTH_EVENT_TYPES
    return await list_experience_events(
        limit=limit,
        event_types=event_types,
        entity_types=(
            ExperienceEntityType.SKILL_GROWTH.value,
            ExperienceEntityType.EVOLUTION.value,
        ),
        since=since,
    )


async def summarize_skill_growth_events(
    *,
    days: int | None = None,
) -> SkillGrowthLedgerSummary:
    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    entity_types = (
        ExperienceEntityType.SKILL_GROWTH.value,
        ExperienceEntityType.EVOLUTION.value,
    )
    total_events = await count_experience_events(
        event_types=SKILL_GROWTH_EVENT_TYPES,
        entity_types=entity_types,
        since=since,
    )
    positive_events = await count_experience_events(
        event_types=SKILL_GROWTH_POSITIVE_EVENT_TYPES,
        entity_types=entity_types,
        since=since,
    )
    negative_events = await count_experience_events(
        event_types=SKILL_GROWTH_NEGATIVE_EVENT_TYPES,
        entity_types=entity_types,
        since=since,
    )
    pending_events = await count_experience_events(
        event_types=SKILL_GROWTH_PENDING_EVENT_TYPES,
        entity_types=entity_types,
        since=since,
    )
    auto_applied = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED.value,
        entity_type=ExperienceEntityType.SKILL_GROWTH.value,
        since=since,
    )
    approved = await count_experience_events(
        event_types=(
            ExperienceEventType.SKILL_GROWTH_APPROVED.value,
            ExperienceEventType.EVOLUTION_APPROVED.value,
        ),
        entity_types=entity_types,
        since=since,
    )
    rejected = await count_experience_events(
        event_types=(
            ExperienceEventType.SKILL_GROWTH_REJECTED.value,
            ExperienceEventType.EVOLUTION_REJECTED.value,
        ),
        entity_types=entity_types,
        since=since,
    )
    blocked = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_BLOCKED.value,
        entity_type=ExperienceEntityType.SKILL_GROWTH.value,
        since=since,
    )
    failed_scan = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_FAILED_SCAN.value,
        entity_type=ExperienceEntityType.SKILL_GROWTH.value,
        since=since,
    )
    apply_failed = await count_experience_events(
        event_type=ExperienceEventType.EVOLUTION_APPLY_FAILED.value,
        entity_type=ExperienceEntityType.EVOLUTION.value,
        since=since,
    )
    return SkillGrowthLedgerSummary(
        total_events=total_events,
        positive_events=positive_events,
        negative_events=negative_events,
        pending_events=pending_events,
        auto_applied=auto_applied,
        approved=approved,
        rejected=rejected,
        blocked=blocked,
        failed_scan=failed_scan,
        apply_failed=apply_failed,
    )
