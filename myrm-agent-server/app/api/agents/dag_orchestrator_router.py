"""REST API router for DAG Visual Orchestrator with Cold Resume and Bidirectional Feedback."""

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.sub_agents.dag_orchestrator import (
    CyclicDependencyError,
    NodeNotFoundError,
)
from app.schemas.dag_orchestrator import (
    DagColdResumeResponse,
    DagExecuteStepRequest,
    DagPlanRequest,
    DagPlanResponse,
    DagRejectLoopbackRequest,
    DagRejectLoopbackResponse,
    DagStatusResponse,
)
from app.services.agent.dag_orchestrator_service import (
    DagNotFoundError,
    DagOrchestratorService,
    get_dag_orchestrator_service,
)

router = APIRouter(prefix="/agents/dag-orchestrator", tags=["DAG Orchestrator"])


@router.post(
    "/plan",
    response_model=DagPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Decompose natural language goal into a multi-agent DAG dependency graph",
)
async def plan_dag(
    req: DagPlanRequest,
    service: DagOrchestratorService = Depends(get_dag_orchestrator_service),
) -> DagPlanResponse:
    """Analyze high-level goal and generate a cycle-free DAG topology with initial ready nodes."""
    try:
        return service.plan_dag(goal=req.goal, dag_id=req.dag_id)
    except CyclicDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid DAG cycle detected: {exc}",
        ) from exc


@router.get(
    "/{dag_id}",
    response_model=DagStatusResponse,
    summary="Get current DAG execution state, node status, and ready set",
)
async def get_dag_status(
    dag_id: str,
    service: DagOrchestratorService = Depends(get_dag_orchestrator_service),
) -> DagStatusResponse:
    """Fetch all node states, ready candidates, and overall progress."""
    try:
        return service.get_dag(dag_id)
    except DagNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{dag_id}/execute-step",
    response_model=DagStatusResponse,
    summary="Advance a ready DAG node to completion and persist checkpoint",
)
async def execute_dag_step(
    dag_id: str,
    req: DagExecuteStepRequest,
    service: DagOrchestratorService = Depends(get_dag_orchestrator_service),
) -> DagStatusResponse:
    """Execute target node and recalculate dependent ready nodes."""
    try:
        return service.execute_step(dag_id=dag_id, node_id=req.node_id)
    except (DagNotFoundError, NodeNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{dag_id}/cold-resume",
    response_model=DagColdResumeResponse,
    summary="Cold-resume execution state from persistent checkpoint without re-running completed nodes",
)
async def cold_resume_dag(
    dag_id: str,
    service: DagOrchestratorService = Depends(get_dag_orchestrator_service),
) -> DagColdResumeResponse:
    """Restore state after sandbox reboot or crash, immediately identifying ready nodes."""
    try:
        return service.cold_resume(dag_id)
    except (DagNotFoundError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{dag_id}/reject",
    response_model=DagRejectLoopbackResponse,
    summary="Trigger bidirectional review loopback: reject upstream node and cascade reset dependents",
)
async def reject_dag_node(
    dag_id: str,
    req: DagRejectLoopbackRequest,
    service: DagOrchestratorService = Depends(get_dag_orchestrator_service),
) -> DagRejectLoopbackResponse:
    """Reject upstream artifact with feedback and reset downstream dependents for bounded dynamic re-planning."""
    try:
        return service.reject_loopback(
            dag_id=dag_id,
            target_node_id=req.target_node_id,
            feedback=req.rejection_feedback,
        )
    except (DagNotFoundError, NodeNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset DAG orchestrator service state (test/maintenance)",
)
async def reset_dag_orchestrator(
    service: DagOrchestratorService = Depends(get_dag_orchestrator_service),
) -> None:
    """Clear all active DAG states and stored checkpoints."""
    service.reset()
