"""Tiered Risk HITL Approval & Dry-Run REST Endpoints.

[INPUT]
- EvaluateTieredRiskRequest, ConfirmTieredExecutionRequest, DryRunSimulationRequest
- myrm_agent_harness.agent.middlewares.approval.tiered_risk_evaluator::TieredRiskEvaluator

[OUTPUT]
- /api/v1/approvals/tiered-risk/evaluate
- /api/v1/approvals/tiered-risk/confirm
- /api/v1/approvals/tiered-risk/dry-run

[POS]
Server API layer for Item 29. Exposes adaptive three-tier risk evaluation,
one-time authorization token validation, and dry-run execution preview.
Strictly under 250 lines. Zero `Any`.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.agent.middlewares.approval.tiered_risk_evaluator import (
    RiskTier,
    TieredRiskEvaluator,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiered-risk", tags=["approvals-tiered-risk"])

_evaluator = TieredRiskEvaluator()

# In-memory single-use token vault for HITL confirmation (single-node sandbox)
# Map: token -> {tool_name, args, created_at, consumed}
_TOKEN_TTL_SECONDS: float = 600.0  # 10 minutes valid
_PENDING_TOKENS: dict[str, dict[str, object]] = {}


class EvaluateTieredRiskRequest(BaseModel):
    """Payload to evaluate execution risk of an action proposal."""

    tool_name: str = Field(..., description="Target tool or action identifier")
    tool_input: dict[str, object] = Field(default_factory=dict, description="Arguments to pass to the tool")
    session_id: str | None = Field(None, description="Optional chat session or thread ID")


class EvaluateTieredRiskResponse(BaseModel):
    """Structured evaluation output determining whether dynamic brake is engaged."""

    tier: RiskTier
    tool_name: str
    target_entity: str | None
    risk_reasons: list[str]
    supports_dry_run: bool
    is_dry_run: bool
    need_confirmation: bool
    confirmation_token: str | None
    suggested_action: str
    param_summary: dict[str, str]


class ConfirmTieredExecutionRequest(BaseModel):
    """Payload to resolve a high-risk confirmation gate."""

    confirmation_token: str = Field(..., description="One-time authorization token issued by evaluation")
    approved: bool = Field(..., description="Whether human operator approved the execution")
    modified_input: dict[str, object] | None = Field(None, description="Modified parameters if edited by operator")
    reason: str | None = Field(None, description="Optional justification or rejection remark")


class ConfirmTieredExecutionResponse(BaseModel):
    """Result of the confirmation decision."""

    decision: Literal["APPROVED", "REJECTED"]
    status: Literal["PROCEED", "ABORTED"]
    tool_name: str
    effective_input: dict[str, object]
    reason: str | None


class DryRunSimulationRequest(BaseModel):
    """Payload to simulate dry-run execution."""

    tool_name: str = Field(..., description="Target tool identifier")
    tool_input: dict[str, object] = Field(default_factory=dict, description="Simulated parameters")


class DryRunSimulationResponse(BaseModel):
    """Output of dry-run simulation preview."""

    simulated: bool
    tool_name: str
    simulated_impact: str
    affected_target: str | None
    predicted_changes: list[str]


def _cleanup_expired_tokens() -> None:
    """Evict expired tokens from the pending token vault."""
    now = time.time()
    expired = [
        tok for tok, record in _PENDING_TOKENS.items()
        if (now - float(record.get("created_at", 0))) > _TOKEN_TTL_SECONDS
    ]
    for tok in expired:
        _PENDING_TOKENS.pop(tok, None)


@router.post("/evaluate", response_model=EvaluateTieredRiskResponse)
async def evaluate_tiered_risk(request: EvaluateTieredRiskRequest) -> EvaluateTieredRiskResponse:
    """Perform three-tier risk evaluation on an upcoming tool invocation."""
    _cleanup_expired_tokens()

    eval_result = _evaluator.evaluate(request.tool_name, request.tool_input)

    # Store token in vault if high-risk brake is triggered
    if eval_result.confirmation_token:
        _PENDING_TOKENS[eval_result.confirmation_token] = {
            "tool_name": request.tool_name,
            "args": request.tool_input,
            "created_at": time.time(),
            "consumed": False,
        }

    return EvaluateTieredRiskResponse(
        tier=eval_result.tier,
        tool_name=eval_result.tool_name,
        target_entity=eval_result.target_entity,
        risk_reasons=list(eval_result.risk_reasons),
        supports_dry_run=eval_result.supports_dry_run,
        is_dry_run=eval_result.is_dry_run,
        need_confirmation=eval_result.need_confirmation,
        confirmation_token=eval_result.confirmation_token,
        suggested_action=eval_result.suggested_action,
        param_summary=eval_result.param_summary,
    )


@router.post("/confirm", response_model=ConfirmTieredExecutionResponse)
async def confirm_tiered_execution(request: ConfirmTieredExecutionRequest) -> ConfirmTieredExecutionResponse:
    """Validate one-time confirmation token and dispatch resume/abort decision."""
    _cleanup_expired_tokens()

    token_record = _PENDING_TOKENS.get(request.confirmation_token)
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Confirmation token not found or expired.",
        )

    if bool(token_record.get("consumed", False)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Confirmation token has already been consumed.",
        )

    # Enforce single-use token consumption
    token_record["consumed"] = True
    _PENDING_TOKENS.pop(request.confirmation_token, None)

    tool_name_raw = token_record.get("tool_name")
    tool_name = str(tool_name_raw) if isinstance(tool_name_raw, str) else "unknown"

    raw_args = token_record.get("args")
    original_args: dict[str, object] = dict(raw_args) if isinstance(raw_args, dict) else {}

    effective_args = request.modified_input if request.modified_input is not None else original_args

    if request.approved:
        return ConfirmTieredExecutionResponse(
            decision="APPROVED",
            status="PROCEED",
            tool_name=tool_name,
            effective_input=effective_args,
            reason=request.reason,
        )

    return ConfirmTieredExecutionResponse(
        decision="REJECTED",
        status="ABORTED",
        tool_name=tool_name,
        effective_input=effective_args,
        reason=request.reason or "Rejected by human operator",
    )


@router.post("/dry-run", response_model=DryRunSimulationResponse)
async def simulate_dry_run(request: DryRunSimulationRequest) -> DryRunSimulationResponse:
    """Simulate tool mutation without applying actual persistent side effects."""
    eval_result = _evaluator.evaluate(request.tool_name, request.tool_input)

    target = eval_result.target_entity or "system"
    verb = request.tool_name.lower().replace("-", "_").split("_")[0]

    return DryRunSimulationResponse(
        simulated=True,
        tool_name=request.tool_name,
        simulated_impact=f"Simulated '{verb}' action targeting '{target}' without persistent mutation.",
        affected_target=target,
        predicted_changes=[
            f"Would affect entity: {target}",
            "Operation mode: dry_run=true",
            f"Risk assessment tier: {eval_result.tier}",
        ],
    )
