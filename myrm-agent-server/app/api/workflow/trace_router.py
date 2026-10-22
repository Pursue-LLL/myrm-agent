"""
[POS] app/api/workflow/trace_router.py
[INPUT] app/schemas/workflow_trace.py, app/services/workflow/trace_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.workflow_trace import (
    ReplayFromNodeRequest,
    ReplayFromNodeResponse,
    WorkflowTraceResponse,
)
from app.services.workflow.trace_service import (
    WorkflowTraceService,
    get_workflow_trace_service,
)

router = APIRouter(prefix="/workflow", tags=["workflow_trace"])


@router.get(
    "/{workflow_id}/trace",
    response_model=WorkflowTraceResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve 5-stage workflow execution trace and holographic node snapshots",
)
def get_workflow_trace(
    workflow_id: str,
    service: WorkflowTraceService = Depends(get_workflow_trace_service),
) -> WorkflowTraceResponse:
    """Fetch ordered node snapshots, token consumptions, and four-dimensional verification scores."""
    return service.get_workflow_trace(workflow_id)


@router.post(
    "/replay-from-node",
    response_model=ReplayFromNodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger breakpoint self-healing replay from selected workflow node",
)
def replay_from_node(
    request: ReplayFromNodeRequest,
    service: WorkflowTraceService = Depends(get_workflow_trace_service),
) -> ReplayFromNodeResponse:
    """Reuse cached parent step artifacts and re-evaluate downstream DAG from the target breakpoint."""
    return service.replay_from_node(request)
