"""Vector dimension guard and rebuild API router.

[INPUT]
- DimGuardInspectRequestDTO, StartRebuildRequestDTO, RebuildTaskStatusResponseDTO.
- VectorDimGuardService singleton dependency.

[OUTPUT]
- APIRouter exposing endpoints for dimension inspection, task-based rebuild initiation, and status tracking.

[POS]
- HTTP controller for Item 151 VectorDimGuardAndRebuildTaskSuite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from myrm_agent_harness.toolkits.memory.vector_dim_guard import TaskLockConflictError

from app.schemas.vector_dim_guard import (
    DimGuardInspectRequestDTO,
    DimGuardInspectResponseDTO,
    RebuildTaskStatusResponseDTO,
    StartRebuildRequestDTO,
)
from app.services.memory.vector_dim_guard_service import (
    VectorDimGuardService,
    get_vector_dim_guard_service,
)

router = APIRouter(prefix="/vector-dim-guard", tags=["Memory: Vector Dim Guard"])


@router.post(
    "/inspect",
    response_model=DimGuardInspectResponseDTO,
    summary="Inspect vector collection existence and dimension alignment",
)
def inspect_collection_dim(
    request: DimGuardInspectRequestDTO,
    service: VectorDimGuardService = Depends(get_vector_dim_guard_service),
) -> DimGuardInspectResponseDTO:
    """Inspect whether a collection exists and matches the expected embedding dimension."""
    return service.inspect_dim(request)


@router.post(
    "/rebuild/start",
    response_model=RebuildTaskStatusResponseDTO,
    summary="Initiate a task-based non-destructive vector index rebuild",
)
def start_vector_rebuild(
    request: StartRebuildRequestDTO,
    service: VectorDimGuardService = Depends(get_vector_dim_guard_service),
) -> RebuildTaskStatusResponseDTO:
    """Start an orchestrated rebuild holding the concurrency lock, preserving data without dropping rows."""
    try:
        return service.start_rebuild(request)
    except TaskLockConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/rebuild/active",
    summary="Get active rebuild task ID holding the execution lock",
)
def get_active_rebuild_task(
    service: VectorDimGuardService = Depends(get_vector_dim_guard_service),
) -> dict[str, str | None]:
    """Check if a rebuild task is currently running and return its task ID."""
    return {"active_task_id": service.get_active_task_id()}


@router.get(
    "/rebuild/{task_id}/status",
    response_model=RebuildTaskStatusResponseDTO,
    summary="Retrieve rebuild task progress snapshot and failed items checklist",
)
def get_rebuild_task_status(
    task_id: str = Path(..., description="Unique task identifier"),
    service: VectorDimGuardService = Depends(get_vector_dim_guard_service),
) -> RebuildTaskStatusResponseDTO:
    """Retrieve detailed execution status and failed item diagnostics for a rebuild task."""
    stat = service.get_task_status(task_id)
    if stat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rebuild task '{task_id}' not found.",
        )
    return stat
