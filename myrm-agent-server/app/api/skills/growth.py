"""Unified skill growth query API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.services.skills.growth_case_types import (
    SkillGrowthCaseDetailRead,
    SkillGrowthCaseStatus,
    SkillGrowthCaseSummaryRead,
    SkillGrowthFormMetadataRead,
)
from app.services.skills.growth_audit_queries import (
    SkillGrowthAuditEntryRead,
    SkillGrowthAuditStatsRead,
    list_skill_growth_audit_entries,
    summarize_skill_growth_audit,
)
from app.services.skills.growth_queries import (
    detail_to_summary,
    get_skill_growth_case_detail,
    list_skill_growth_cases,
    summarize_skill_growth_dashboard_stats,
)

router = APIRouter(prefix="/skill-growth", tags=["skill-growth"])


class SkillGrowthFormMetadataResponse(BaseModel):
    schedule_hint: str | None = None
    form_reasoning: str | None = None


class SkillGrowthCaseSummaryResponse(BaseModel):
    id: str
    source: str
    status: str
    skill_name: str
    skill_id: str | None = None
    growth_type: str
    title: str
    summary: str
    description: str | None = None
    confidence: float | None = None
    test_passed: bool | None = None
    apply_status: str | None = None
    apply_error: str | None = None
    reason_code: str | None = None
    remediation: str | None = None
    runtime_failure: dict[str, object] | None = None
    chat_id: str | None = None
    form_metadata: SkillGrowthFormMetadataResponse | None = None
    has_diff: bool = False
    has_trajectory: bool = False
    has_trigger_condition: bool = False
    has_skill_steps: bool = False
    created_at: str


class SkillGrowthCaseDetailResponse(SkillGrowthCaseSummaryResponse):
    trigger_condition: str | None = None
    skill_steps: str | None = None
    original_content: str | None = None
    proposed_content: str | None = None
    trajectory: str | None = None


class SkillGrowthCaseListResponse(BaseModel):
    items: list[SkillGrowthCaseSummaryResponse]
    total: int


class SkillGrowthDashboardStatsResponse(BaseModel):
    total: int
    pending_review: int
    auto_applied: int
    blocked: int


class SkillGrowthAuditEntryResponse(BaseModel):
    event_id: str
    case_id: str
    source: str
    status: str
    skill_name: str
    skill_id: str | None = None
    growth_type: str
    reason: str
    confidence: float | None = None
    severity: str | None = None
    reason_code: str | None = None
    remediation: str | None = None
    created_at: str


class SkillGrowthAuditListResponse(BaseModel):
    items: list[SkillGrowthAuditEntryResponse]
    total: int


class SkillGrowthAuditBucketResponse(BaseModel):
    key: str
    count: int
    percentage: float


class SkillGrowthAuditSkillBucketResponse(BaseModel):
    skill_name: str
    skill_id: str | None = None
    count: int
    percentage: float


class SkillGrowthAuditStatsResponse(BaseModel):
    total_events: int
    avg_confidence: float
    by_status: list[SkillGrowthAuditBucketResponse] = Field(default_factory=list)
    top_skills: list[SkillGrowthAuditSkillBucketResponse] = Field(default_factory=list)
    time_range_days: int


def _form_metadata_response(
    metadata: SkillGrowthFormMetadataRead | None,
) -> SkillGrowthFormMetadataResponse | None:
    if metadata is None:
        return None
    return SkillGrowthFormMetadataResponse(
        schedule_hint=metadata.schedule_hint,
        form_reasoning=metadata.form_reasoning,
    )


def _summary_response(item: SkillGrowthCaseSummaryRead) -> SkillGrowthCaseSummaryResponse:
    return SkillGrowthCaseSummaryResponse(
        id=item.id,
        source=item.source.value,
        status=item.status.value,
        skill_name=item.skill_name,
        skill_id=item.skill_id,
        growth_type=item.growth_type,
        title=item.title,
        summary=item.summary,
        description=item.description,
        confidence=item.confidence,
        test_passed=item.test_passed,
        apply_status=item.apply_status,
        apply_error=item.apply_error,
        reason_code=item.reason_code,
        remediation=item.remediation,
        runtime_failure=(
            item.runtime_failure.model_dump(mode="json") if item.runtime_failure is not None else None
        ),
        chat_id=item.chat_id,
        form_metadata=_form_metadata_response(item.form_metadata),
        has_diff=item.has_diff,
        has_trajectory=item.has_trajectory,
        has_trigger_condition=item.has_trigger_condition,
        has_skill_steps=item.has_skill_steps,
        created_at=item.created_at.isoformat(),
    )


def _detail_response(item: SkillGrowthCaseDetailRead) -> SkillGrowthCaseDetailResponse:
    summary = _summary_response(detail_to_summary(item))
    return SkillGrowthCaseDetailResponse(
        **summary.model_dump(),
        trigger_condition=item.trigger_condition,
        skill_steps=item.skill_steps,
        original_content=item.original_content,
        proposed_content=item.proposed_content,
        trajectory=item.trajectory,
    )


def _audit_entry_response(
    item: SkillGrowthAuditEntryRead,
) -> SkillGrowthAuditEntryResponse:
    return SkillGrowthAuditEntryResponse(
        event_id=item.event_id,
        case_id=item.case_id,
        source=item.source.value,
        status=item.status.value,
        skill_name=item.skill_name,
        skill_id=item.skill_id,
        growth_type=item.growth_type,
        reason=item.reason,
        confidence=item.confidence,
        severity=item.severity,
        reason_code=item.reason_code,
        remediation=item.remediation,
        created_at=item.created_at.isoformat(),
    )


def _audit_stats_response(
    stats: SkillGrowthAuditStatsRead,
) -> SkillGrowthAuditStatsResponse:
    return SkillGrowthAuditStatsResponse(
        total_events=stats.total_events,
        avg_confidence=stats.avg_confidence,
        by_status=[
            SkillGrowthAuditBucketResponse(
                key=item.key,
                count=item.count,
                percentage=item.percentage,
            )
            for item in stats.by_status
        ],
        top_skills=[
            SkillGrowthAuditSkillBucketResponse(
                skill_name=item.skill_name,
                skill_id=item.skill_id,
                count=item.count,
                percentage=item.percentage,
            )
            for item in stats.top_skills
        ],
        time_range_days=stats.time_range_days,
    )


@router.get("/cases")
async def get_skill_growth_cases(
    status: SkillGrowthCaseStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    items, total = await list_skill_growth_cases(limit=limit, offset=offset, status=status)
    payload = SkillGrowthCaseListResponse(
        items=[_summary_response(item) for item in items],
        total=total,
    )
    return success_response(data=payload.model_dump())


@router.get("/cases/{case_id}")
async def get_skill_growth_case(case_id: str) -> JSONResponse:
    item = await get_skill_growth_case_detail(case_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Skill growth case not found: {case_id}")
    return success_response(data=_detail_response(item).model_dump())


@router.get("/stats")
async def get_skill_growth_stats() -> JSONResponse:
    stats = await summarize_skill_growth_dashboard_stats()
    payload = SkillGrowthDashboardStatsResponse(
        total=stats.total,
        pending_review=stats.pending_review,
        auto_applied=stats.auto_applied,
        blocked=stats.blocked,
    )
    return success_response(data=payload.model_dump())


@router.get("/audit")
async def get_skill_growth_audit(
    limit: int = Query(50, ge=1, le=200),
    days: int = Query(30, ge=1, le=365),
    skill_id: str | None = Query(None),
) -> JSONResponse:
    items = await list_skill_growth_audit_entries(limit=limit, days=days, skill_id=skill_id)
    payload = SkillGrowthAuditListResponse(
        items=[_audit_entry_response(item) for item in items],
        total=len(items),
    )
    return success_response(data=payload.model_dump())


@router.get("/audit/stats")
async def get_skill_growth_audit_stats(
    time_range_days: int = Query(30, ge=1, le=365),
) -> JSONResponse:
    stats = await summarize_skill_growth_audit(time_range_days=time_range_days)
    return success_response(data=_audit_stats_response(stats).model_dump())
