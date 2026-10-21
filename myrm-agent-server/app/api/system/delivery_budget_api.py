"""
[INPUT]: Trial execution events, unmetered usage overrides, and budget adjustment commands.
[OUTPUT]: CumulativeDeliveryLedger aggregates, trial breakdown logs, and budget gate verdicts.
[POS]: myrm-agent/myrm-agent-server/app/api/system/delivery_budget_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.cumulative_delivery_budget import (
    CumulativeDeliveryLedger,
    CumulativeDeliveryLedgerManager,
    DeliveryBudgetGate,
    TrialRecord,
    UnknownUsageStatus,
)

router = APIRouter(tags=["delivery-budget"])

_manager = CumulativeDeliveryLedgerManager(
    default_imputed_prompt_tokens=1500,
    default_imputed_completion_tokens=500,
    default_imputed_cost_usd=0.006,
)


class RecordTrialRequest(BaseModel):
    delivery_id: str
    trial_id: str
    agent_id: str
    agent_role: str
    attempt_index: int
    step_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    is_unmetered: bool = False
    unmetered_status: str = "METERED"
    custom_imputed_prompt_tokens: Optional[int] = None
    custom_imputed_completion_tokens: Optional[int] = None
    custom_imputed_cost_usd: Optional[float] = None
    budget_tokens_limit: Optional[int] = None
    budget_cost_limit_usd: Optional[float] = None
    status: str = "success"


class AdjustBudgetRequest(BaseModel):
    additional_tokens: int = 0
    additional_cost_usd: float = 0.0
    set_budget_tokens_limit: Optional[int] = None
    set_budget_cost_limit_usd: Optional[float] = None
    force_unpause: bool = True


class TrialRecordSchema(BaseModel):
    trial_id: str
    agent_id: str
    agent_role: str
    attempt_index: int
    step_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    is_unmetered: bool
    unmetered_status: str
    imputed_prompt_tokens: int
    imputed_completion_tokens: int
    imputed_cost_usd: float
    effective_tokens: int
    effective_cost_usd: float
    status: str
    created_at: str


class CumulativeDeliveryLedgerResponse(BaseModel):
    delivery_id: str
    title: str
    budget_tokens_limit: Optional[int] = None
    budget_cost_limit_usd: Optional[float] = None
    total_metered_tokens: int
    total_imputed_tokens: int
    total_effective_tokens: int
    total_metered_cost_usd: float
    total_imputed_cost_usd: float
    total_effective_cost_usd: float
    unmetered_trials_count: int
    total_trials_count: int
    gate_verdict: str
    is_paused: bool
    pause_reason: Optional[str] = None
    trials: List[TrialRecordSchema]
    created_at: str
    updated_at: str


def _convert_trial_to_schema(t: TrialRecord) -> TrialRecordSchema:
    return TrialRecordSchema(
        trial_id=t.trial_id,
        agent_id=t.agent_id,
        agent_role=t.agent_role,
        attempt_index=t.attempt_index,
        step_name=t.step_name,
        prompt_tokens=t.prompt_tokens,
        completion_tokens=t.completion_tokens,
        total_tokens=t.total_tokens,
        cost_usd=t.cost_usd,
        latency_ms=t.latency_ms,
        is_unmetered=t.is_unmetered,
        unmetered_status=t.unmetered_status.value
        if hasattr(t.unmetered_status, "value")
        else str(t.unmetered_status),
        imputed_prompt_tokens=t.imputed_prompt_tokens,
        imputed_completion_tokens=t.imputed_completion_tokens,
        imputed_cost_usd=t.imputed_cost_usd,
        effective_tokens=t.effective_tokens,
        effective_cost_usd=t.effective_cost_usd,
        status=t.status,
        created_at=t.created_at,
    )


def _convert_ledger_to_response(
    ledger: CumulativeDeliveryLedger,
) -> CumulativeDeliveryLedgerResponse:
    return CumulativeDeliveryLedgerResponse(
        delivery_id=ledger.delivery_id,
        title=ledger.title,
        budget_tokens_limit=ledger.budget_tokens_limit,
        budget_cost_limit_usd=ledger.budget_cost_limit_usd,
        total_metered_tokens=ledger.total_metered_tokens,
        total_imputed_tokens=ledger.total_imputed_tokens,
        total_effective_tokens=ledger.total_effective_tokens,
        total_metered_cost_usd=ledger.total_metered_cost_usd,
        total_imputed_cost_usd=ledger.total_imputed_cost_usd,
        total_effective_cost_usd=ledger.total_effective_cost_usd,
        unmetered_trials_count=ledger.unmetered_trials_count,
        total_trials_count=ledger.total_trials_count,
        gate_verdict=ledger.gate_verdict.value,
        is_paused=ledger.is_paused,
        pause_reason=ledger.pause_reason,
        trials=[_convert_trial_to_schema(t) for t in ledger.trials],
        created_at=ledger.created_at,
        updated_at=ledger.updated_at,
    )


@router.post(
    "/delivery-budget/record-trial",
    response_model=CumulativeDeliveryLedgerResponse,
    status_code=status.HTTP_200_OK,
)
async def record_trial(req: RecordTrialRequest) -> CumulativeDeliveryLedgerResponse:
    """Records a single worker attempt and updates the cumulative delivery ledger."""
    unmetered_enum = UnknownUsageStatus.METERED
    try:
        unmetered_enum = UnknownUsageStatus(req.unmetered_status)
    except ValueError:
        unmetered_enum = UnknownUsageStatus.METERED

    ledger = _manager.record_trial(
        delivery_id=req.delivery_id,
        trial_id=req.trial_id,
        agent_id=req.agent_id,
        agent_role=req.agent_role,
        attempt_index=req.attempt_index,
        step_name=req.step_name,
        prompt_tokens=req.prompt_tokens,
        completion_tokens=req.completion_tokens,
        cost_usd=req.cost_usd,
        latency_ms=req.latency_ms,
        is_unmetered=req.is_unmetered,
        unmetered_status=unmetered_enum,
        custom_imputed_prompt_tokens=req.custom_imputed_prompt_tokens,
        custom_imputed_completion_tokens=req.custom_imputed_completion_tokens,
        custom_imputed_cost_usd=req.custom_imputed_cost_usd,
        budget_tokens_limit=req.budget_tokens_limit,
        budget_cost_limit_usd=req.budget_cost_limit_usd,
        status=req.status,
    )
    return _convert_ledger_to_response(ledger)


@router.get(
    "/delivery-budget/{delivery_id}",
    response_model=CumulativeDeliveryLedgerResponse,
    status_code=status.HTTP_200_OK,
)
async def get_delivery_ledger(
    delivery_id: str = Path(..., description="Target delivery run identifier"),
) -> CumulativeDeliveryLedgerResponse:
    """Retrieves full cumulative ledger, trial breakdowns, and unmetered audit info."""
    ledger = _manager.get_ledger(delivery_id)
    if not ledger:
        ledger = _manager.create_or_get_ledger(
            delivery_id=delivery_id,
            title=f"Delivery Lifecycle ({delivery_id})",
        )
    return _convert_ledger_to_response(ledger)


@router.post(
    "/delivery-budget/{delivery_id}/adjust-budget",
    response_model=CumulativeDeliveryLedgerResponse,
    status_code=status.HTTP_200_OK,
)
async def adjust_delivery_budget(
    delivery_id: str = Path(..., description="Target delivery run identifier"),
    req: AdjustBudgetRequest = ...,
) -> CumulativeDeliveryLedgerResponse:
    """Appends budget capacity to a delivery run and optionally clears fuse pause."""
    try:
        ledger = _manager.append_budget(
            delivery_id=delivery_id,
            additional_tokens=req.additional_tokens,
            additional_cost_usd=req.additional_cost_usd,
            set_budget_tokens_limit=req.set_budget_tokens_limit,
            set_budget_cost_limit_usd=req.set_budget_cost_limit_usd,
            force_unpause=req.force_unpause,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery run {delivery_id} not found",
        )
    return _convert_ledger_to_response(ledger)
