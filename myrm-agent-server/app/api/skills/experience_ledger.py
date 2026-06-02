"""
[INPUT]
- app.database.models::ExperienceLedgerEvent (POS: 技能域模型。管理技能进化审批、迁移审批、学习资产事件。)
- app.services.skills.experience_ledger::list_experience_events (POS: 学习资产事件账本服务)
- app.services.skills.growth_projection_queries::list_skill_growth_projection_events (POS: 技能成长账本投影查询层)
[OUTPUT]
- Experience ledger list API and skill-growth projection APIs
[POS]
经验账本接口层。对外暴露原始 ledger 事件查询，以及 skill-growth projection 事件/摘要查询。
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.database.models import ExperienceLedgerEvent
from app.services.skills.experience_ledger import (
    count_experience_events,
    list_experience_events,
)
from app.services.skills.growth_projection_queries import (
    SkillGrowthProjectionEventRead,
    list_skill_growth_projection_events,
    summarize_skill_growth_projection,
)

router = APIRouter(prefix="/experience-ledger", tags=["experience-ledger"])


class ExperienceLedgerEventResponse(BaseModel):
    id: str
    event_type: str
    entity_type: str
    entity_id: str
    lineage_id: str
    outcome: str | None = None
    summary: str
    artifact_refs: dict[str, object] = Field(default_factory=dict)
    metrics_snapshot: dict[str, object] = Field(default_factory=dict)
    detail: dict[str, object] = Field(default_factory=dict)
    created_at: str


class ExperienceLedgerListResponse(BaseModel):
    items: list[ExperienceLedgerEventResponse]
    total: int


class SkillGrowthLedgerEventResponse(BaseModel):
    event_id: str
    case_id: str
    status: str
    source: str
    skill_name: str
    skill_id: str | None = None
    growth_type: str
    summary: str
    created_at: str


class SkillGrowthLedgerEventListResponse(BaseModel):
    items: list[SkillGrowthLedgerEventResponse]
    total: int


class SkillGrowthLedgerSummaryResponse(BaseModel):
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
    by_status: dict[str, int] = Field(default_factory=dict)


def _to_response(item: ExperienceLedgerEvent) -> ExperienceLedgerEventResponse:
    return ExperienceLedgerEventResponse(
        id=item.id,
        event_type=item.event_type,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        lineage_id=item.lineage_id,
        outcome=item.outcome,
        summary=item.summary,
        artifact_refs=item.artifact_refs,
        metrics_snapshot=item.metrics_snapshot,
        detail=item.detail,
        created_at=item.created_at.isoformat(),
    )


def _to_skill_growth_projection(item: SkillGrowthProjectionEventRead) -> SkillGrowthLedgerEventResponse:
    return SkillGrowthLedgerEventResponse(
        event_id=item.event_id,
        case_id=item.case_id,
        status=item.status,
        source=item.source,
        skill_name=item.skill_name,
        skill_id=item.skill_id,
        growth_type=item.growth_type,
        summary=item.summary,
        created_at=item.created_at.isoformat(),
    )


@router.get("/events", response_model=ExperienceLedgerListResponse)
async def get_experience_ledger_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None),
    entity_type: str | None = Query(None),
    lineage_id: str | None = Query(None),
) -> ExperienceLedgerListResponse:
    items = await list_experience_events(
        limit=limit,
        event_type=event_type,
        entity_type=entity_type,
        lineage_id=lineage_id,
    )
    total = await count_experience_events(
        event_type=event_type,
        entity_type=entity_type,
        lineage_id=lineage_id,
    )
    return ExperienceLedgerListResponse(items=[_to_response(item) for item in items], total=total)


@router.get("/skill-growth/events", response_model=SkillGrowthLedgerEventListResponse)
async def get_skill_growth_projection_events(
    limit: int = Query(50, ge=1, le=200),
    negative_only: bool = Query(False),
    days: int | None = Query(None, ge=1, le=365),
) -> SkillGrowthLedgerEventListResponse:
    items, total = await list_skill_growth_projection_events(
        limit=limit,
        negative_only=negative_only,
        days=days,
    )
    return SkillGrowthLedgerEventListResponse(
        items=[_to_skill_growth_projection(item) for item in items],
        total=total,
    )


@router.get("/skill-growth/summary", response_model=SkillGrowthLedgerSummaryResponse)
async def get_skill_growth_projection_summary(
    days: int | None = Query(None, ge=1, le=365),
) -> SkillGrowthLedgerSummaryResponse:
    summary = await summarize_skill_growth_projection(days=days)
    return SkillGrowthLedgerSummaryResponse(
        total_events=summary.total_events,
        pending_events=summary.pending_events,
        positive_events=summary.positive_events,
        negative_events=summary.negative_events,
        auto_applied=summary.auto_applied,
        approved=summary.approved,
        rejected=summary.rejected,
        blocked=summary.blocked,
        failed_scan=summary.failed_scan,
        apply_failed=summary.apply_failed,
        by_status=summary.by_status,
    )
