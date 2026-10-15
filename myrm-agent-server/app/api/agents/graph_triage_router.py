from fastapi import APIRouter, Path

from app.schemas.graph_triage import (
    BudgetEstimateRequest,
    BudgetEstimateResponse,
    ConfigureGuardRequest,
    ExecutionSpendResponse,
    PartialReduceRequest,
    PartialReduceResponse,
    SpendUpdateRequest,
    TriageAssessmentRequest,
    TriageAssessmentResponse,
)
from app.services.agent.graph_triage_service import GraphTriageService

router = APIRouter(prefix="/agents/graph-triage", tags=["Graph Triage & Budget Guard"])


@router.post("/assess", response_model=TriageAssessmentResponse)
async def assess_task_applicability(
    request: TriageAssessmentRequest,
) -> TriageAssessmentResponse:
    """Evaluate task prompt and subtasks to triage whether graph orchestration is appropriate."""
    service = GraphTriageService.get_instance()
    return service.assess_task(prompt=request.prompt, subtasks=request.subtasks)


@router.post("/estimate-budget", response_model=BudgetEstimateResponse)
async def estimate_fanout_budget(
    request: BudgetEstimateRequest,
) -> BudgetEstimateResponse:
    """Estimate token and cost usage before executing fan-out, checking hard caps."""
    service = GraphTriageService.get_instance()
    return service.estimate_budget(
        node_count=request.node_count,
        fanout_concurrency=request.fanout_concurrency,
        prompt_tokens=request.prompt_tokens,
        estimated_tokens_per_node=request.estimated_tokens_per_node,
        max_tokens_cap=request.max_tokens_cap,
        max_cost_usd_cap=request.max_cost_usd_cap,
    )


@router.post("/sessions/{session_id}/configure", response_model=ExecutionSpendResponse)
async def configure_session_guard(
    session_id: str = Path(..., description="Unique session identifier"),
    request: ConfigureGuardRequest = ...,  # type: ignore[assignment]
) -> ExecutionSpendResponse:
    """Configure hard cap, warning/critical thresholds, and initial concurrency."""
    service = GraphTriageService.get_instance()
    return service.configure_session(
        session_id=session_id,
        max_tokens=request.max_tokens,
        max_cost_usd=request.max_cost_usd,
        warning_threshold_pct=request.warning_threshold_pct,
        critical_threshold_pct=request.critical_threshold_pct,
        initial_concurrency=request.initial_concurrency,
    )


@router.post("/sessions/{session_id}/update-spend", response_model=ExecutionSpendResponse)
async def update_session_spend(
    session_id: str = Path(..., description="Unique session identifier"),
    request: SpendUpdateRequest = ...,  # type: ignore[assignment]
) -> ExecutionSpendResponse:
    """Report incremental token/cost consumption, updating throttle and circuit breaker state."""
    service = GraphTriageService.get_instance()
    return service.update_spend(
        session_id=session_id,
        incremental_tokens=request.incremental_tokens,
        incremental_cost_usd=request.incremental_cost_usd,
    )


@router.get("/sessions/{session_id}/status", response_model=ExecutionSpendResponse)
async def get_session_budget_status(
    session_id: str = Path(..., description="Unique session identifier"),
) -> ExecutionSpendResponse:
    """Get current spend, remaining budget, and concurrency throttle status."""
    service = GraphTriageService.get_instance()
    return service.get_spend_status(session_id=session_id)


@router.post("/sessions/{session_id}/early-reduce", response_model=PartialReduceResponse)
async def execute_early_reduce(
    session_id: str = Path(..., description="Unique session identifier"),
    request: PartialReduceRequest = ...,  # type: ignore[assignment]
) -> PartialReduceResponse:
    """Trigger graceful partial early reduce on completed nodes when budget is constrained."""
    service = GraphTriageService.get_instance()
    return service.perform_early_reduce(
        session_id=session_id,
        total_planned_tokens=request.total_planned_tokens,
        nodes=request.nodes,
    )
