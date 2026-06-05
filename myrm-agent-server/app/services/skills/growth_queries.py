"""Unified skill growth query service.

Combines current growth cases from approval-backed draft/evolution records and
ledger-backed audit/timeline queries for all skill-growth surfaces.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import desc, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, ExperienceLedgerEvent
from app.services.skills.evolution_reviews import (
    EvolutionReviewRecord,
    RuntimeFailureEvidence,
    list_evolution_review_records,
)
from app.services.skills.experience_ledger import (
    SKILL_GROWTH_EVENT_TYPES,
    SKILL_GROWTH_NEGATIVE_EVENT_TYPES,
    ExperienceEntityType,
    get_skill_growth_event_status,
)

SKILL_GROWTH_CASE_ACTION_TYPES: tuple[str, ...] = (
    "skill_draft",
    "skill_patch",
    "semantic_memory",
)


class SkillGrowthCaseSource(StrEnum):
    DRAFT = "draft"
    EVOLUTION = "evolution"


class SkillGrowthCaseStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    AUTO_APPLIED = "AUTO_APPLIED"
    FAILED_SCAN = "FAILED_SCAN"
    BLOCKED_LOCKED = "BLOCKED_LOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLY_FAILED = "APPLY_FAILED"


@dataclass(slots=True)
class SkillGrowthCaseRead:
    id: str
    source: SkillGrowthCaseSource
    status: SkillGrowthCaseStatus
    skill_name: str
    skill_id: str | None
    growth_type: str
    title: str
    summary: str
    description: str | None
    trigger_condition: str | None
    skill_steps: str | None
    original_content: str | None
    proposed_content: str | None
    confidence: float | None
    test_passed: bool | None
    apply_status: str | None
    apply_error: str | None
    reason_code: str | None
    remediation: str | None
    runtime_failure: RuntimeFailureEvidence | None
    trajectory: str | None
    created_at: datetime


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


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _approval_growth_status(record: ApprovalRecord) -> SkillGrowthCaseStatus:
    payload = _payload_dict(record.payload)
    payload_status = _text(payload.get("growth_status"))
    if payload_status is not None:
        try:
            return SkillGrowthCaseStatus(payload_status)
        except ValueError:
            return SkillGrowthCaseStatus.PENDING_REVIEW
    if record.status == "APPROVED":
        return SkillGrowthCaseStatus.APPROVED
    if record.status == "REJECTED":
        return SkillGrowthCaseStatus.REJECTED
    return SkillGrowthCaseStatus.PENDING_REVIEW


def _approval_case(record: ApprovalRecord) -> SkillGrowthCaseRead:
    payload = _payload_dict(record.payload)
    draft_name = _text(payload.get("skill_name")) or record.action_type
    description = _text(record.reason) or _text(payload.get("description"))
    summary = (
        description
        or _text(payload.get("trigger_condition"))
        or _text(payload.get("skill_steps"))
        or _text(payload.get("patch_content"))
        or _text(payload.get("content"))
        or draft_name
    )
    return SkillGrowthCaseRead(
        id=f"draft:{record.id}",
        source=SkillGrowthCaseSource.DRAFT,
        status=_approval_growth_status(record),
        skill_name=draft_name,
        skill_id=None,
        growth_type=record.action_type,
        title=draft_name,
        summary=summary,
        description=description,
        trigger_condition=_text(payload.get("trigger_condition")),
        skill_steps=_text(payload.get("skill_steps")),
        original_content=None,
        proposed_content=_text(payload.get("patch_content")) or _text(payload.get("content")),
        confidence=_float_value(payload.get("confidence")),
        test_passed=_bool_value(payload.get("test_passed")),
        apply_status=None,
        apply_error=None,
        reason_code=_text(payload.get("reason_code")),
        remediation=_text(payload.get("remediation")),
        runtime_failure=None,
        trajectory=None,
        created_at=record.created_at,
    )


def _evolution_case(record: EvolutionReviewRecord) -> SkillGrowthCaseRead:
    return SkillGrowthCaseRead(
        id=f"evolution:{record.id}",
        source=SkillGrowthCaseSource.EVOLUTION,
        status=SkillGrowthCaseStatus(record.status.value),
        skill_name=record.skill_name,
        skill_id=record.skill_id,
        growth_type=record.evolution_type,
        title=record.skill_name,
        summary=record.reason,
        description=record.reason,
        trigger_condition=None,
        skill_steps=None,
        original_content=record.original_content,
        proposed_content=record.evolved_content,
        confidence=record.confidence,
        test_passed=record.test_passed,
        apply_status=record.apply_status.value,
        apply_error=record.apply_error,
        reason_code=record.reason_code,
        remediation=record.remediation,
        runtime_failure=record.runtime_failure,
        trajectory=record.trajectory,
        created_at=record.created_at,
    )


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


async def _load_approval_cases() -> list[SkillGrowthCaseRead]:
    async with get_session() as db:
        result = await db.execute(
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type.in_(SKILL_GROWTH_CASE_ACTION_TYPES))
            .order_by(desc(ApprovalRecord.created_at))
        )
        records = list(result.scalars().all())
    return [_approval_case(record) for record in records]


async def _load_evolution_cases() -> list[SkillGrowthCaseRead]:
    records = await list_evolution_review_records(limit=1000, pending_only=False)
    return [_evolution_case(record) for record in records]


async def list_skill_growth_cases(
    *,
    limit: int = 50,
    offset: int = 0,
    status: SkillGrowthCaseStatus | None = None,
) -> tuple[list[SkillGrowthCaseRead], int]:
    approval_cases, evolution_cases = await asyncio.gather(
        _load_approval_cases(),
        _load_evolution_cases(),
    )
    items = [*approval_cases, *evolution_cases]
    if status is not None:
        items = [item for item in items if item.status == status]
    items.sort(key=lambda item: item.created_at, reverse=True)
    total = len(items)
    return items[offset : offset + limit], total


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
