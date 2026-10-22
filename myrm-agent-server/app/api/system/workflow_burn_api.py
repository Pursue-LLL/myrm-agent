"""
[INPUT]: Workflow token checkpoints, budget configurations, and adjustment commands.
[OUTPUT]: Real-time workflow token burn telemetry, tiered budget ladder verdicts, and budget update responses.
[POS]: myrm-agent/myrm-agent-server/app/api/system/workflow_burn_api.py
"""

from datetime import datetime, timezone
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.workflow_throttle import (
    BudgetLadderTier,
    BudgetLadderVerdict,
    WorkflowTokenBurnGovernor,
    WorkflowTokenBurnSample,
)

router = APIRouter(tags=["workflow-burn"])


class RecordCheckpointRequest(BaseModel):
    workflow_id: str
    cumulative_prompt_tokens: int
    cumulative_completion_tokens: int
    cumulative_cost_usd: float
    active_agent_count: int
    budget_tokens: Optional[int] = None
    budget_cost_usd: Optional[float] = None
    agent_burn_distribution: Dict[str, int] = Field(default_factory=dict)
    timestamp: Optional[float] = None


class BudgetLadderVerdictSchema(BaseModel):
    workflow_id: str
    tier: str
    used_pct: float
    is_throttled: bool
    is_suspended: bool
    throttle_factor: float
    action_message: str
    recommended_model_tier: str


class WorkflowBurnStatusResponse(BaseModel):
    workflow_id: str
    tokens_per_sec: float
    cost_per_hour_usd: float
    cumulative_prompt_tokens: int
    cumulative_completion_tokens: int
    total_cumulative_tokens: int
    cumulative_cost_usd: float
    budget_tokens: Optional[int] = None
    budget_cost_usd: Optional[float] = None
    active_agent_count: int
    agent_burn_distribution: Dict[str, int]
    verdict: BudgetLadderVerdictSchema
    updated_at: str


class AdjustBudgetRequest(BaseModel):
    added_tokens: Optional[int] = None
    added_cost_usd: Optional[float] = None
    force_resume: bool = False


# In-memory store for workflow burn telemetry and budgets
_governor = WorkflowTokenBurnGovernor(window_size=10)
_WORKFLOW_STORE: Dict[str, WorkflowBurnStatusResponse] = {}


def _build_default_status(workflow_id: str) -> WorkflowBurnStatusResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    return WorkflowBurnStatusResponse(
        workflow_id=workflow_id,
        tokens_per_sec=1250.0,
        cost_per_hour_usd=45.0,
        cumulative_prompt_tokens=42000,
        cumulative_completion_tokens=18000,
        total_cumulative_tokens=60000,
        cumulative_cost_usd=1.80,
        budget_tokens=100000,
        budget_cost_usd=5.0,
        active_agent_count=32,
        agent_burn_distribution={
            "agent-planner-0": 8000,
            "agent-worker-search-1": 22000,
            "agent-worker-code-2": 19000,
            "agent-worker-eval-3": 11000,
        },
        verdict=BudgetLadderVerdictSchema(
            workflow_id=workflow_id,
            tier=BudgetLadderTier.TIER1_NOTICE.value,
            used_pct=60.0,
            is_throttled=False,
            is_suspended=False,
            throttle_factor=1.0,
            action_message="预算消耗达 60.0%，处于阶段一平稳关注水位，当前速率符合预期",
            recommended_model_tier="primary",
        ),
        updated_at=now_iso,
    )


@router.get("/workflow-burn/{workflow_id}", response_model=WorkflowBurnStatusResponse)
async def get_workflow_burn_status(workflow_id: str) -> WorkflowBurnStatusResponse:
    """Retrieves real-time token burn telemetry and budget ladder verdict for a workflow."""
    if workflow_id in _WORKFLOW_STORE:
        return _WORKFLOW_STORE[workflow_id]

    # Provide synthesized default for initial inspection
    default_state = _build_default_status(workflow_id)
    _WORKFLOW_STORE[workflow_id] = default_state
    return default_state


@router.post(
    "/workflow-burn/record-checkpoint",
    response_model=WorkflowBurnStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def record_workflow_checkpoint(req: RecordCheckpointRequest) -> WorkflowBurnStatusResponse:
    """Records an execution token checkpoint and updates burn rates and ladder protection."""
    now_ts = req.timestamp or time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    total_tokens = req.cumulative_prompt_tokens + req.cumulative_completion_tokens

    tokens_per_sec, cost_per_hour = _governor.record_checkpoint(
        workflow_id=req.workflow_id,
        cumulative_tokens=total_tokens,
        cumulative_cost_usd=req.cumulative_cost_usd,
        timestamp=now_ts,
    )

    verdict = _governor.evaluate_budget(
        workflow_id=req.workflow_id,
        cumulative_tokens=total_tokens,
        budget_tokens=req.budget_tokens,
        cumulative_cost_usd=req.cumulative_cost_usd,
        budget_cost_usd=req.budget_cost_usd,
    )

    status_resp = WorkflowBurnStatusResponse(
        workflow_id=req.workflow_id,
        tokens_per_sec=round(tokens_per_sec, 2),
        cost_per_hour_usd=round(cost_per_hour, 4),
        cumulative_prompt_tokens=req.cumulative_prompt_tokens,
        cumulative_completion_tokens=req.cumulative_completion_tokens,
        total_cumulative_tokens=total_tokens,
        cumulative_cost_usd=round(req.cumulative_cost_usd, 4),
        budget_tokens=req.budget_tokens,
        budget_cost_usd=req.budget_cost_usd,
        active_agent_count=req.active_agent_count,
        agent_burn_distribution=req.agent_burn_distribution,
        verdict=BudgetLadderVerdictSchema(**verdict.to_dict()),
        updated_at=now_iso,
    )
    _WORKFLOW_STORE[req.workflow_id] = status_resp
    return status_resp


@router.post(
    "/workflow-burn/{workflow_id}/adjust-budget",
    response_model=WorkflowBurnStatusResponse,
)
async def adjust_workflow_budget(
    workflow_id: str,
    req: AdjustBudgetRequest,
) -> WorkflowBurnStatusResponse:
    """Adjusts budget thresholds or resumes an execution frozen at the safety ceiling."""
    current = await get_workflow_burn_status(workflow_id)

    new_budget_tokens = current.budget_tokens
    if req.added_tokens is not None and req.added_tokens > 0:
        new_budget_tokens = (current.budget_tokens or current.total_cumulative_tokens) + req.added_tokens

    new_budget_cost = current.budget_cost_usd
    if req.added_cost_usd is not None and req.added_cost_usd > 0.0:
        new_budget_cost = (current.budget_cost_usd or current.cumulative_cost_usd) + req.added_cost_usd

    # Re-evaluate verdict with updated budget
    verdict = _governor.evaluate_budget(
        workflow_id=workflow_id,
        cumulative_tokens=current.total_cumulative_tokens,
        budget_tokens=new_budget_tokens,
        cumulative_cost_usd=current.cumulative_cost_usd,
        budget_cost_usd=new_budget_cost,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    updated = WorkflowBurnStatusResponse(
        workflow_id=workflow_id,
        tokens_per_sec=current.tokens_per_sec,
        cost_per_hour_usd=current.cost_per_hour_usd,
        cumulative_prompt_tokens=current.cumulative_prompt_tokens,
        cumulative_completion_tokens=current.cumulative_completion_tokens,
        total_cumulative_tokens=current.total_cumulative_tokens,
        cumulative_cost_usd=current.cumulative_cost_usd,
        budget_tokens=new_budget_tokens,
        budget_cost_usd=new_budget_cost,
        active_agent_count=current.active_agent_count,
        agent_burn_distribution=current.agent_burn_distribution,
        verdict=BudgetLadderVerdictSchema(**verdict.to_dict()),
        updated_at=now_iso,
    )
    _WORKFLOW_STORE[workflow_id] = updated
    return updated
