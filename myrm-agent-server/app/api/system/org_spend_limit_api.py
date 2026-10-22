"""
[INPUT]: Organization IDs, query labels, budget configurations, and token expenditure payloads.
[OUTPUT]: SpendGovernorDecisionResponse verdicts, OrgSpendSummaryResponse stats, and IdentAttributionResponse reports.
[POS]: myrm-agent/myrm-agent-server/app/api/system/org_spend_limit_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.org_spend_limit import (
    BillingScope,
    GovernorAction,
    IdentSpendAttribution,
    OrgMonthlySpendRecord,
    OrgSharedAgentSpendGovernor,
    QuerySpendLabel,
    SpendGovernorDecision,
    SpendLimitConfig,
    SpendSurface,
)

router = APIRouter(tags=["org-spend-limit"])

_governor = OrgSharedAgentSpendGovernor()


# --- Pydantic Schemas ---

class ConfigureOrgBudgetRequest(BaseModel):
    org_id: str
    monthly_budget_usd: float = Field(default=100.0, gt=0.0)
    soft_warn_watermark_pct: float = Field(default=80.0, ge=10.0, le=100.0)
    hard_block_limit_usd: float = Field(default=100.0, gt=0.0)
    is_circuit_breaker_enabled: bool = True


class QuerySpendLabelPayload(BaseModel):
    org_id: str
    surface: str = "CHANNEL"  # CHANNEL | DIRECT_MESSAGE | REST_API | AUTOMATED_CI
    billing_scope: str = "ORG_SHARED"  # ORG_SHARED | PERSONAL_DM
    session_id: str
    requesting_user_id: str
    query_tags: List[str] = Field(default_factory=list)


class PreCheckSpendRequest(BaseModel):
    org_id: str
    estimated_cost_usd: float = Field(default=0.01, ge=0.0)
    label: QuerySpendLabelPayload


class SpendGovernorDecisionResponse(BaseModel):
    action: str
    current_spend_usd: float
    monthly_budget_usd: float
    utilization_pct: float
    reason: str
    is_blocked: bool


class RecordSpendRequest(BaseModel):
    org_id: str
    actual_tokens: int = Field(ge=0)
    actual_cost_usd: float = Field(ge=0.0)
    label: QuerySpendLabelPayload


class OrgMonthlySpendRecordResponse(BaseModel):
    record_id: str
    org_id: str
    tokens_consumed: int
    cost_usd: float
    requesting_user_id: str
    surface: str
    billing_scope: str
    recorded_at: str


class OrgSpendSummaryResponse(BaseModel):
    monthly_budget_usd: float
    current_spend_usd: float
    remaining_budget_usd: float
    utilization_pct: float
    total_records_count: float


class IdentAttributionResponse(BaseModel):
    requesting_user_id: str
    total_calls_count: int
    total_tokens: int
    total_spend_usd: float
    surfaces_breakdown: Dict[str, float]
    primary_surface: str


# --- Converters ---

def _convert_label(p: QuerySpendLabelPayload) -> QuerySpendLabel:
    surface_enum = (
        SpendSurface.DIRECT_MESSAGE
        if p.surface == "DIRECT_MESSAGE"
        else SpendSurface.REST_API
        if p.surface == "REST_API"
        else SpendSurface.AUTOMATED_CI
        if p.surface == "AUTOMATED_CI"
        else SpendSurface.CHANNEL
    )
    scope_enum = (
        BillingScope.PERSONAL_DM
        if p.billing_scope == "PERSONAL_DM"
        else BillingScope.ORG_SHARED
    )
    return QuerySpendLabel(
        org_id=p.org_id,
        surface=surface_enum,
        billing_scope=scope_enum,
        session_id=p.session_id,
        requesting_user_id=p.requesting_user_id,
        query_tags=p.query_tags,
    )


# --- HTTP Endpoints ---

@router.post(
    "/org-spend-limit/configure",
    summary="配置组织月度 AI Agent 预算限额与硬熔断门禁",
)
def configure_org_budget(payload: ConfigureOrgBudgetRequest) -> Dict[str, str]:
    config = SpendLimitConfig(
        org_id=payload.org_id,
        monthly_budget_usd=payload.monthly_budget_usd,
        soft_warn_watermark_pct=payload.soft_warn_watermark_pct,
        hard_block_limit_usd=payload.hard_block_limit_usd,
        is_circuit_breaker_enabled=payload.is_circuit_breaker_enabled,
    )
    _governor.configure_org_budget(config)
    return {"status": "ok", "org_id": payload.org_id}


@router.post(
    "/org-spend-limit/pre-check",
    response_model=SpendGovernorDecisionResponse,
    summary="智能体执行前组织预算水位预检 (支持群聊公摊 vs 私聊个人分级治理与 100% 熔断刹车)",
)
def pre_check_spend(payload: PreCheckSpendRequest) -> SpendGovernorDecisionResponse:
    label = _convert_label(payload.label)
    decision = _governor.pre_check_and_guard(
        org_id=payload.org_id,
        estimated_cost_usd=payload.estimated_cost_usd,
        label=label,
    )
    return SpendGovernorDecisionResponse(
        action=decision.action.value,
        current_spend_usd=decision.current_spend_usd,
        monthly_budget_usd=decision.monthly_budget_usd,
        utilization_pct=decision.utilization_pct,
        reason=decision.reason,
        is_blocked=decision.is_blocked,
    )


@router.post(
    "/org-spend-limit/record-spend",
    response_model=OrgMonthlySpendRecordResponse,
    summary="上报单次 Query 真实算力 Token 消耗与身份标签绑定流水",
)
def record_spend(payload: RecordSpendRequest) -> OrgMonthlySpendRecordResponse:
    label = _convert_label(payload.label)
    rec = _governor.record_spend(
        org_id=payload.org_id,
        actual_tokens=payload.actual_tokens,
        actual_cost_usd=payload.actual_cost_usd,
        label=label,
    )
    return OrgMonthlySpendRecordResponse(
        record_id=rec.record_id,
        org_id=rec.org_id,
        tokens_consumed=rec.tokens_consumed,
        cost_usd=rec.cost_usd,
        requesting_user_id=rec.label.requesting_user_id,
        surface=rec.label.surface.value,
        billing_scope=rec.label.billing_scope.value,
        recorded_at=rec.recorded_at,
    )


@router.get(
    "/org-spend-limit/summary/{org_id}",
    response_model=OrgSpendSummaryResponse,
    summary="查询组织当前月度支出总览、预算余额与水位百分比",
)
def get_org_summary(org_id: str) -> OrgSpendSummaryResponse:
    data = _governor.get_org_summary(org_id)
    return OrgSpendSummaryResponse(
        monthly_budget_usd=data["monthly_budget_usd"],
        current_spend_usd=data["current_spend_usd"],
        remaining_budget_usd=data["remaining_budget_usd"],
        utilization_pct=data["utilization_pct"],
        total_records_count=data["total_records_count"],
    )


@router.get(
    "/org-spend-limit/attributions/{org_id}",
    response_model=List[IdentAttributionResponse],
    summary="查询组织内按 ident:<id> 身份命名空间与 Surface 聚合归因对账排行",
)
def get_user_attributions(org_id: str) -> List[IdentAttributionResponse]:
    items = _governor.get_user_attributions(org_id)
    return [
        IdentAttributionResponse(
            requesting_user_id=i.requesting_user_id,
            total_calls_count=i.total_calls_count,
            total_tokens=i.total_tokens,
            total_spend_usd=i.total_spend_usd,
            surfaces_breakdown=i.surfaces_breakdown,
            primary_surface=i.primary_surface,
        )
        for i in items
    ]
