"""
[INPUT]
- app.database.models::ExperienceLedgerEvent (POS: 技能域模型。管理技能进化审批、迁移审批、学习资产事件。)
- app.services.skills.experience_ledger::list_experience_events (POS: 学习资产事件账本服务)
- app.services.skills.experience_ledger::count_experience_events (POS: 学习资产事件账本服务)
[OUTPUT]
- SkillGrowthProjectionEventRead / SkillGrowthProjectionSummaryRead / projection query helpers
[POS]
技能成长账本投影查询层。负责把 `skill_growth.*` ledger 事件规范化为前端可消费的事件列表与摘要，避免 API 层重复实现状态与来源映射。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.database.models import ExperienceLedgerEvent
from app.services.skills.experience_ledger import (
    SKILL_GROWTH_STATUS_MAP,
    ExperienceEntityType,
    ExperienceEventType,
    count_experience_events,
    list_experience_events,
)

SKILL_GROWTH_PROJECTION_EVENT_TYPES: tuple[str, ...] = (
    ExperienceEventType.SKILL_GROWTH_REVIEW_REQUIRED.value,
    ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED.value,
    ExperienceEventType.SKILL_GROWTH_APPROVED.value,
    ExperienceEventType.SKILL_GROWTH_REJECTED.value,
    ExperienceEventType.SKILL_GROWTH_BLOCKED.value,
    ExperienceEventType.SKILL_GROWTH_FAILED_SCAN.value,
    ExperienceEventType.EVOLUTION_APPLY_FAILED.value,
)

SKILL_GROWTH_PROJECTION_NEGATIVE_EVENT_TYPES: tuple[str, ...] = (
    ExperienceEventType.SKILL_GROWTH_REJECTED.value,
    ExperienceEventType.SKILL_GROWTH_BLOCKED.value,
    ExperienceEventType.SKILL_GROWTH_FAILED_SCAN.value,
    ExperienceEventType.EVOLUTION_APPLY_FAILED.value,
)

SKILL_GROWTH_PROJECTION_POSITIVE_EVENT_TYPES: tuple[str, ...] = (
    ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED.value,
    ExperienceEventType.SKILL_GROWTH_APPROVED.value,
)

SKILL_GROWTH_PROJECTION_ENTITY_TYPES: tuple[str, ...] = (
    ExperienceEntityType.SKILL_GROWTH.value,
    ExperienceEntityType.EVOLUTION.value,
)


@dataclass(slots=True)
class SkillGrowthProjectionEventRead:
    event_id: str
    case_id: str
    status: str
    source: str
    skill_name: str
    skill_id: str | None
    growth_type: str
    summary: str
    created_at: datetime


@dataclass(slots=True)
class SkillGrowthProjectionSummaryRead:
    total_events: int
    pending_events: int
    positive_events: int
    negative_events: int
    auto_applied: int
    approved: int
    rejected: int
    blocked: int
    failed_scan: int
    apply_failed: int
    by_status: dict[str, int] = field(default_factory=dict)


def _payload_dict(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _projection_status(event_type: str) -> str:
    return SKILL_GROWTH_STATUS_MAP.get(event_type, "UNKNOWN")


def _projection_source(entity_type: str) -> str:
    return "evolution" if entity_type == ExperienceEntityType.EVOLUTION.value else "draft"


def _projection_skill_name(event: ExperienceLedgerEvent) -> str:
    artifact_refs = _payload_dict(event.artifact_refs)
    detail = _payload_dict(event.detail)
    return (
        _text(artifact_refs.get("skill_name"))
        or _text(detail.get("skill_name"))
        or _text(detail.get("skill_id"))
        or "Unknown skill"
    )


def _projection_skill_id(event: ExperienceLedgerEvent) -> str | None:
    artifact_refs = _payload_dict(event.artifact_refs)
    detail = _payload_dict(event.detail)
    return _text(artifact_refs.get("skill_id")) or _text(detail.get("skill_id"))


def _projection_growth_type(event: ExperienceLedgerEvent) -> str:
    artifact_refs = _payload_dict(event.artifact_refs)
    detail = _payload_dict(event.detail)
    return (
        _text(detail.get("evolution_type"))
        or _text(detail.get("draft_type"))
        or _text(artifact_refs.get("draft_type"))
        or "unknown"
    )


def _to_projection_event(event: ExperienceLedgerEvent) -> SkillGrowthProjectionEventRead:
    return SkillGrowthProjectionEventRead(
        event_id=event.id,
        case_id=event.entity_id,
        status=_projection_status(event.event_type),
        source=_projection_source(event.entity_type),
        skill_name=_projection_skill_name(event),
        skill_id=_projection_skill_id(event),
        growth_type=_projection_growth_type(event),
        summary=event.summary,
        created_at=event.created_at,
    )


async def list_skill_growth_projection_events(
    *,
    limit: int = 50,
    negative_only: bool = False,
    days: int | None = None,
) -> tuple[list[SkillGrowthProjectionEventRead], int]:
    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    event_types = SKILL_GROWTH_PROJECTION_NEGATIVE_EVENT_TYPES if negative_only else SKILL_GROWTH_PROJECTION_EVENT_TYPES
    events = await list_experience_events(
        limit=limit,
        event_types=event_types,
        entity_types=SKILL_GROWTH_PROJECTION_ENTITY_TYPES,
        since=since,
    )
    total = await count_experience_events(
        event_types=event_types,
        entity_types=SKILL_GROWTH_PROJECTION_ENTITY_TYPES,
        since=since,
    )
    return ([_to_projection_event(event) for event in events], total)


async def summarize_skill_growth_projection(
    *,
    days: int | None = None,
) -> SkillGrowthProjectionSummaryRead:
    since = datetime.now(UTC) - timedelta(days=days) if days is not None else None
    entity_type = ExperienceEntityType.SKILL_GROWTH.value
    total_events = await count_experience_events(
        event_types=SKILL_GROWTH_PROJECTION_EVENT_TYPES,
        entity_types=SKILL_GROWTH_PROJECTION_ENTITY_TYPES,
        since=since,
    )
    pending_events = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_REVIEW_REQUIRED.value,
        entity_type=entity_type,
        since=since,
    )
    positive_events = await count_experience_events(
        event_types=SKILL_GROWTH_PROJECTION_POSITIVE_EVENT_TYPES,
        entity_types=SKILL_GROWTH_PROJECTION_ENTITY_TYPES,
        since=since,
    )
    negative_events = await count_experience_events(
        event_types=SKILL_GROWTH_PROJECTION_NEGATIVE_EVENT_TYPES,
        entity_types=SKILL_GROWTH_PROJECTION_ENTITY_TYPES,
        since=since,
    )
    auto_applied = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_AUTO_APPLIED.value,
        entity_type=entity_type,
        since=since,
    )
    approved = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_APPROVED.value,
        entity_type=entity_type,
        since=since,
    )
    rejected = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_REJECTED.value,
        entity_type=entity_type,
        since=since,
    )
    blocked = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_BLOCKED.value,
        entity_type=entity_type,
        since=since,
    )
    failed_scan = await count_experience_events(
        event_type=ExperienceEventType.SKILL_GROWTH_FAILED_SCAN.value,
        entity_type=entity_type,
        since=since,
    )
    apply_failed = await count_experience_events(
        event_type=ExperienceEventType.EVOLUTION_APPLY_FAILED.value,
        entity_type=ExperienceEntityType.EVOLUTION.value,
        since=since,
    )
    return SkillGrowthProjectionSummaryRead(
        total_events=total_events,
        pending_events=pending_events,
        positive_events=positive_events,
        negative_events=negative_events,
        auto_applied=auto_applied,
        approved=approved,
        rejected=rejected,
        blocked=blocked,
        failed_scan=failed_scan,
        apply_failed=apply_failed,
        by_status={
            "PENDING_REVIEW": pending_events,
            "AUTO_APPLIED": auto_applied,
            "APPROVED": approved,
            "REJECTED": rejected,
            "BLOCKED_LOCKED": blocked,
            "FAILED_SCAN": failed_scan,
            "APPLY_FAILED": apply_failed,
        },
    )
