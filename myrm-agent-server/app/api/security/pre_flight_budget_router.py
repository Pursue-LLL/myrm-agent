"""FastAPI router for Live Pre-Flight Budget Chokepoint Suite.

[INPUT]
fastapi::APIRouter, Query, status
app.schemas.pre_flight_budget::BudgetConfigCreateRequest, RecordSpendRequest, EvaluateBudgetRequest
app.services.security.pre_flight_budget_service::PreFlightBudgetService

[OUTPUT]
router: APIRouter instance exposing /pre-flight-budget endpoints.

[POS]
运行前预算卡点安全路由层。暴露预算配置、支出记录、实时预检评估与事件队列消费端点。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.pre_flight_budget import (
    BudgetBroadcastEventResponse,
    BudgetConfigCreateRequest,
    BudgetConfigResponse,
    BudgetDecisionResponse,
    EvaluateBudgetRequest,
    QueueAllowedResponse,
    RecordSpendRequest,
    SpendRecordResponse,
)
from app.services.security.pre_flight_budget_service import PreFlightBudgetService

router = APIRouter(
    prefix="/pre-flight-budget",
    tags=["Pre-Flight Budget Security"],
)


@router.post(
    "/config",
    response_model=BudgetConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set or update live project budget configuration",
)
def set_budget_config(
    request: BudgetConfigCreateRequest,
) -> BudgetConfigResponse:
    """Configure live project budget."""
    service = PreFlightBudgetService.get_instance()
    return service.set_config(request)


@router.get(
    "/config/{project_id}",
    response_model=BudgetConfigResponse,
    summary="Get live project budget configuration",
)
def get_budget_config(project_id: str) -> BudgetConfigResponse:
    """Retrieve live configuration for a project."""
    service = PreFlightBudgetService.get_instance()
    cfg = service.get_config(project_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No budget configuration found for project {project_id}",
        )
    return cfg


@router.post(
    "/spend",
    response_model=SpendRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record spend in project ledger and broadcast event",
)
def record_spend(request: RecordSpendRequest) -> SpendRecordResponse:
    """Append a spend record to project ledger."""
    service = PreFlightBudgetService.get_instance()
    return service.record_spend(request)


@router.post(
    "/evaluate",
    response_model=BudgetDecisionResponse,
    summary="Evaluate live budget status without hard exception",
)
def evaluate_budget(
    request: EvaluateBudgetRequest,
) -> BudgetDecisionResponse:
    """Evaluate whether project is over budget right now."""
    service = PreFlightBudgetService.get_instance()
    return service.evaluate(request.project_id)


@router.post(
    "/enforce",
    response_model=BudgetDecisionResponse,
    summary="Enforce pre-flight budget chokepoint before LLM call",
)
def enforce_budget(
    request: EvaluateBudgetRequest,
) -> BudgetDecisionResponse:
    """Enforce pre-flight budget chokepoint; returns decision with tripped status."""
    service = PreFlightBudgetService.get_instance()
    decision = service.enforce(request.project_id)
    if decision.tripped:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Pre-flight budget limit breached",
                "decision": decision.model_dump(),
            },
        )
    return decision


@router.get(
    "/queue-allowed/{project_id}",
    response_model=QueueAllowedResponse,
    summary="Check if task queue dispatching is allowed",
)
def check_queue_dispatch_allowed(project_id: str) -> QueueAllowedResponse:
    """Check queue dispatch lock status."""
    service = PreFlightBudgetService.get_instance()
    return service.is_queue_dispatch_allowed(project_id)


@router.get(
    "/events",
    response_model=list[BudgetBroadcastEventResponse],
    summary="Get recent budget broadcast events",
)
def get_broadcast_events(
    project_id: str | None = Query(default=None, description="Optional project filter"),
    limit: int = Query(default=50, ge=1, le=500, description="Max events to return"),
) -> list[BudgetBroadcastEventResponse]:
    """Retrieve broadcast event stream history."""
    service = PreFlightBudgetService.get_instance()
    return service.get_events(project_id=project_id, limit=limit)
