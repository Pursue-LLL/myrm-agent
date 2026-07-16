"""[INPUT]
- app.database.models::ApprovalRecord, SkillGrowthCase (POS: ORM models for growth audit)
- app.services.skills.evolution_reviews::EvolutionReviewRecord (POS: review record DTO)

[OUTPUT]
- get_growth_audit_timeline(): paginated audit trail of skill growth events
- get_growth_case_stats(): aggregated statistics for growth case dashboard

[POS]
Ledger-backed skill growth audit and timeline queries.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from app.database.connection import get_session
from app.database.models import ExperienceLedgerEvent
from app.services.skills.experience_ledger import (
    SKILL_GROWTH_EVENT_TYPES,
    SKILL_GROWTH_NEGATIVE_EVENT_TYPES,
    ExperienceEntityType,
    get_skill_growth_event_status,
)
from app.services.skills.growth_case_types import SkillGrowthCaseSource, SkillGrowthCaseStatus


@dataclass(slots=True)
class SkillGrowthAuditEntryRead:
    event_id: str
    case_id: str
    source: SkillGrowthCaseSource
    status: SkillGrowthCaseStatus
    skill_name: str
    skill_id: str | None
    growth_type: str
    reason: str
    confidence: float | None
    severity: str | None
    reason_code: str | None
    remediation: str | None
    created_at: datetime


@dataclass(slots=True)
class SkillGrowthAuditBucketRead:
    key: str
    count: int
    percentage: float


@dataclass(slots=True)
class SkillGrowthAuditSkillBucketRead:
    skill_name: str
    skill_id: str | None
    count: int
    percentage: float


@dataclass(slots=True)
class SkillGrowthAuditStatsRead:
    total_events: int
    avg_confidence: float
    by_status: list[SkillGrowthAuditBucketRead]
    top_skills: list[SkillGrowthAuditSkillBucketRead]
    time_range_days: int


@dataclass(slots=True)
class SkillGrowthTimelineEventRead:
    case_id: str
    source: SkillGrowthCaseSource
    status: SkillGrowthCaseStatus
    skill_name: str
    skill_id: str | None
    growth_type: str
    created_at: datetime
    change_summary: str


def _payload_dict(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _event_skill_name(event: ExperienceLedgerEvent) -> str:
    artifact_refs = _payload_dict(event.artifact_refs)
    detail = _payload_dict(event.detail)
    return (
        _text(artifact_refs.get("skill_name"))
        or _text(detail.get("skill_name"))
        or _text(detail.get("skill_id"))
        or "Unknown skill"
    )


def _event_skill_id(event: ExperienceLedgerEvent) -> str | None:
    artifact_refs = _payload_dict(event.artifact_refs)
    detail = _payload_dict(event.detail)
    return _text(artifact_refs.get("skill_id")) or _text(detail.get("skill_id"))


def _event_growth_type(event: ExperienceLedgerEvent) -> str:
    artifact_refs = _payload_dict(event.artifact_refs)
    detail = _payload_dict(event.detail)
    return (
        _text(detail.get("evolution_type"))
        or _text(artifact_refs.get("draft_type"))
        or _text(detail.get("draft_type"))
        or "unknown"
    )


def _event_status(event: ExperienceLedgerEvent) -> SkillGrowthCaseStatus | None:
    status = get_skill_growth_event_status(event.event_type)
    if status is None:
        return None
    return SkillGrowthCaseStatus(status)


def _event_source(event: ExperienceLedgerEvent) -> SkillGrowthCaseSource:
    if event.entity_type == ExperienceEntityType.EVOLUTION.value:
        return SkillGrowthCaseSource.EVOLUTION
    return SkillGrowthCaseSource.DRAFT


async def list_skill_growth_timeline(
    *,
    limit: int = 20,
    days: int | None = None,
) -> list[SkillGrowthTimelineEventRead]:
    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    async with get_session() as db:
        stmt = (
            select(ExperienceLedgerEvent)
            .where(ExperienceLedgerEvent.event_type.in_(SKILL_GROWTH_EVENT_TYPES))
            .where(
                ExperienceLedgerEvent.entity_type.in_(
                    (
                        ExperienceEntityType.SKILL_GROWTH.value,
                        ExperienceEntityType.EVOLUTION.value,
                    )
                )
            )
            .order_by(desc(ExperienceLedgerEvent.created_at))
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(ExperienceLedgerEvent.created_at >= since)
        result = await db.execute(stmt)
        events = list(result.scalars().all())

    timeline: list[SkillGrowthTimelineEventRead] = []
    for event in events:
        status = _event_status(event)
        if status is None:
            continue
        timeline.append(
            SkillGrowthTimelineEventRead(
                case_id=event.entity_id,
                source=_event_source(event),
                status=status,
                skill_name=_event_skill_name(event),
                skill_id=_event_skill_id(event),
                growth_type=_event_growth_type(event),
                created_at=event.created_at,
                change_summary=event.summary,
            )
        )
    return timeline


async def list_skill_growth_audit_entries(
    *,
    limit: int = 50,
    days: int | None = None,
    skill_id: str | None = None,
) -> list[SkillGrowthAuditEntryRead]:
    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    fetch_limit = max(limit * 4, 200)
    async with get_session() as db:
        stmt = (
            select(ExperienceLedgerEvent)
            .where(ExperienceLedgerEvent.event_type.in_(SKILL_GROWTH_NEGATIVE_EVENT_TYPES))
            .where(
                ExperienceLedgerEvent.entity_type.in_(
                    (
                        ExperienceEntityType.SKILL_GROWTH.value,
                        ExperienceEntityType.EVOLUTION.value,
                    )
                )
            )
            .order_by(desc(ExperienceLedgerEvent.created_at))
            .limit(fetch_limit)
        )
        if since is not None:
            stmt = stmt.where(ExperienceLedgerEvent.created_at >= since)
        result = await db.execute(stmt)
        events = list(result.scalars().all())

    items: list[SkillGrowthAuditEntryRead] = []
    for event in events:
        event_skill_id = _event_skill_id(event)
        if skill_id is not None and event_skill_id != skill_id:
            continue
        status = _event_status(event)
        if status is None:
            continue
        detail = _payload_dict(event.detail)
        items.append(
            SkillGrowthAuditEntryRead(
                event_id=event.id,
                case_id=event.entity_id,
                source=_event_source(event),
                status=status,
                skill_name=_event_skill_name(event),
                skill_id=event_skill_id,
                growth_type=_event_growth_type(event),
                reason=_text(detail.get("reject_reason")) or event.summary,
                confidence=_float_value(_payload_dict(event.metrics_snapshot).get("confidence")),
                severity=_text(detail.get("severity")),
                reason_code=_text(detail.get("reason_code")),
                remediation=_text(detail.get("remediation")),
                created_at=event.created_at,
            )
        )
        if len(items) >= limit:
            break
    return items


async def summarize_skill_growth_audit(
    *,
    time_range_days: int = 30,
) -> SkillGrowthAuditStatsRead:
    items = await list_skill_growth_audit_entries(limit=1000, days=time_range_days)
    if not items:
        return SkillGrowthAuditStatsRead(
            total_events=0,
            avg_confidence=0.0,
            by_status=[],
            top_skills=[],
            time_range_days=time_range_days,
        )

    confidence_values = [item.confidence for item in items if item.confidence is not None]
    avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0

    status_counts = Counter(item.status.value for item in items)
    top_skills_counter = Counter((item.skill_name, item.skill_id) for item in items)
    total = len(items)

    return SkillGrowthAuditStatsRead(
        total_events=total,
        avg_confidence=round(avg_confidence, 2),
        by_status=[
            SkillGrowthAuditBucketRead(
                key=status,
                count=count,
                percentage=round(count / total * 100, 2),
            )
            for status, count in status_counts.most_common()
        ],
        top_skills=[
            SkillGrowthAuditSkillBucketRead(
                skill_name=skill_name,
                skill_id=skill_id,
                count=count,
                percentage=round(count / total * 100, 2),
            )
            for (skill_name, skill_id), count in top_skills_counter.most_common(10)
        ],
        time_range_days=time_range_days,
    )
