"""
[INPUT]: Token evaluate requests, drift audit parameters, and budget guard evaluation requests.
[OUTPUT]: Real-time cache savings ROI metrics, historical unit cost drift alerts, and circuit breaker trip states.
[POS]: myrm-agent/myrm-agent-server/app/api/system/token_economics_api.py
"""

from typing import Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.token_economics import (
    BudgetGuardPolicy,
    CacheRoiCalculator,
    DriftReasonType,
    GuardStatus,
    RunawayCostGuard,
    TokenUsageSnapshot,
    UnitCostDriftDetector,
)

router = APIRouter(tags=["token-economics"])

_calculator = CacheRoiCalculator()
_drift_detector = UnitCostDriftDetector(max_samples=30, drift_threshold_pct=20.0)


class TokenEvaluateRequest(BaseModel):
    task_id: str = Field(..., description="Unique task run identifier")
    model_name: str = Field(default="deepseek-chat", description="Model invoked")
    task_category: str = Field(default="general_coding", description="Category for grouping")
    total_prompt_tokens: int = Field(default=0, ge=0)
    cached_prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    execution_duration_seconds: float = Field(default=1.0, ge=0.0)


class CacheSavingsResponse(BaseModel):
    task_id: str
    model_name: str
    cache_hit_rate_pct: float
    baseline_cost_rmb: float
    actual_cost_rmb: float
    saved_amount_rmb: float
    saved_percentage: float
    burn_rate_rmb_per_minute: float


class DriftAuditRequest(BaseModel):
    model_name: str = Field(..., description="Model identifier")
    task_category: str = Field(..., description="Task business category")
    total_tokens: int = Field(..., ge=0)
    actual_cost_rmb: float = Field(..., ge=0.0)
    cache_hit_rate_pct: float = Field(..., ge=0.0, le=100.0)
    is_routed_fallback: bool = Field(default=False)


class CostDriftAlertResponse(BaseModel):
    task_category: str
    model_name: str
    current_unit_cost_per_k: float
    baseline_unit_cost_per_k: float
    drift_percentage: float
    is_significant_drift: bool
    reason: str
    explanation: str


class BudgetPolicySchema(BaseModel):
    max_allowed_cost_rmb: float = 10.0
    soft_warning_threshold_rmb: float = 7.0
    max_allowed_tokens: int = 200_000
    max_burn_rate_rmb_per_minute: float = 3.0


class GuardCheckRequest(BaseModel):
    current_cost_rmb: float = Field(..., ge=0.0)
    current_tokens: int = Field(..., ge=0)
    duration_seconds: float = Field(..., ge=0.0)
    policy: Optional[BudgetPolicySchema] = None


class BudgetGuardEvaluationResponse(BaseModel):
    status: str
    current_cost_rmb: float
    current_burn_rate_rmb_min: float
    current_tokens: int
    is_paused: bool
    reason: str
    suggested_action: str


@router.post(
    "/token-economics/evaluate",
    response_model=CacheSavingsResponse,
    status_code=status.HTTP_200_OK,
)
async def evaluate_token_economics(req: TokenEvaluateRequest) -> CacheSavingsResponse:
    """Evaluates real-time token cost, prompt-cache savings ROI, and burn rate."""
    snapshot = TokenUsageSnapshot(
        task_id=req.task_id,
        model_name=req.model_name,
        task_category=req.task_category,
        total_prompt_tokens=req.total_prompt_tokens,
        cached_prompt_tokens=req.cached_prompt_tokens,
        completion_tokens=req.completion_tokens,
        execution_duration_seconds=req.execution_duration_seconds,
    )
    metrics = _calculator.calculate_savings(snapshot)

    duration_mins = max(0.1 / 60.0, req.execution_duration_seconds / 60.0)
    burn_rate = round(metrics.actual_cost_rmb / duration_mins, 4)

    return CacheSavingsResponse(
        task_id=metrics.task_id,
        model_name=metrics.model_name,
        cache_hit_rate_pct=metrics.cache_hit_rate_pct,
        baseline_cost_rmb=metrics.baseline_cost_rmb,
        actual_cost_rmb=metrics.actual_cost_rmb,
        saved_amount_rmb=metrics.saved_amount_rmb,
        saved_percentage=metrics.saved_percentage,
        burn_rate_rmb_per_minute=burn_rate,
    )


@router.post(
    "/token-economics/drift-audit",
    response_model=CostDriftAlertResponse,
    status_code=status.HTTP_200_OK,
)
async def audit_cost_drift(req: DriftAuditRequest) -> CostDriftAlertResponse:
    """Detects unit-cost baseline drift (>20%) and provides root-cause attribution."""
    alert = _drift_detector.record_and_evaluate(
        model_name=req.model_name,
        task_category=req.task_category,
        total_tokens=req.total_tokens,
        actual_cost_rmb=req.actual_cost_rmb,
        cache_hit_rate_pct=req.cache_hit_rate_pct,
        is_routed_fallback=req.is_routed_fallback,
    )
    return CostDriftAlertResponse(
        task_category=alert.task_category,
        model_name=alert.model_name,
        current_unit_cost_per_k=alert.current_unit_cost_per_k,
        baseline_unit_cost_per_k=alert.baseline_unit_cost_per_k,
        drift_percentage=alert.drift_percentage,
        is_significant_drift=alert.is_significant_drift,
        reason=alert.reason.value if hasattr(alert.reason, "value") else str(alert.reason),
        explanation=alert.explanation,
    )


@router.post(
    "/token-economics/guard-check",
    response_model=BudgetGuardEvaluationResponse,
    status_code=status.HTTP_200_OK,
)
async def evaluate_budget_guard(req: GuardCheckRequest) -> BudgetGuardEvaluationResponse:
    """Evaluates runaway cost guard policies and determines whether to trip circuit breakers."""
    if req.policy:
        policy = BudgetGuardPolicy(
            max_allowed_cost_rmb=req.policy.max_allowed_cost_rmb,
            soft_warning_threshold_rmb=req.policy.soft_warning_threshold_rmb,
            max_allowed_tokens=req.policy.max_allowed_tokens,
            max_burn_rate_rmb_per_minute=req.policy.max_burn_rate_rmb_per_minute,
        )
    else:
        policy = BudgetGuardPolicy()

    eval_result = RunawayCostGuard.evaluate(
        policy=policy,
        current_cost_rmb=req.current_cost_rmb,
        current_tokens=req.current_tokens,
        duration_seconds=req.duration_seconds,
    )

    return BudgetGuardEvaluationResponse(
        status=eval_result.status.value if hasattr(eval_result.status, "value") else str(eval_result.status),
        current_cost_rmb=eval_result.current_cost_rmb,
        current_burn_rate_rmb_min=eval_result.current_burn_rate_rmb_min,
        current_tokens=eval_result.current_tokens,
        is_paused=eval_result.is_paused,
        reason=eval_result.reason,
        suggested_action=eval_result.suggested_action,
    )
