"""
[POS] app/api/security/host_execution_guard_router.py
[INPUT] app.schemas.host_execution_guard, app.services.security.host_execution_guard_service
[OUTPUT] router

FastAPI router for Local Host Safe Execution Sandbox & Non-Destructive Guardrail Suite.
Exposes endpoints for host path shielding, command AST safety verification,
and atomic workspace COW snapshotting and rollback.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.host_execution_guard import (
    ApproveCommandRequest,
    CreateSnapshotRequest,
    HostExecutionGuardMetricsResponse,
    InspectCommandRequest,
    InspectCommandResponse,
    InspectPathRequest,
    InspectPathResponse,
    RejectCommandRequest,
    RollbackSnapshotRequest,
    WorkspaceSnapshotResponse,
)
from app.services.security.host_execution_guard_service import (
    HostExecutionGuardService,
    get_host_execution_guard_service,
)

router = APIRouter(
    prefix="/host-execution-guard",
    tags=["Local Host Safe Execution Sandbox & Non-Destructive Guardrail"],
)


@router.post(
    "/paths/inspect",
    response_model=InspectPathResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect host filesystem path access and enforce mechanical protection or redirection",
)
def inspect_path(
    request: InspectPathRequest,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> InspectPathResponse:
    """Evaluate target path against system root locks and scratch overlay rules."""
    return service.inspect_path(request)


@router.post(
    "/commands/inspect",
    response_model=InspectCommandResponse,
    status_code=status.HTTP_200_OK,
    summary="Statically analyze shell command string for catastrophic or high-risk patterns",
)
def inspect_command(
    request: InspectCommandRequest,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> InspectCommandResponse:
    """Statically verify command against destructive blacklist and HITL requirements."""
    return service.inspect_command(request)


@router.post(
    "/commands/approve",
    response_model=InspectCommandResponse,
    status_code=status.HTTP_200_OK,
    summary="User operator confirms and approves a pending high-risk shell command",
)
def approve_command(
    request: ApproveCommandRequest,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> InspectCommandResponse:
    """Authorize execution of an inspected command flagged for human review."""
    try:
        return service.approve_command(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending command inspection '{request.inspection_id}' not found.",
        ) from err


@router.post(
    "/commands/reject",
    response_model=InspectCommandResponse,
    status_code=status.HTTP_200_OK,
    summary="User operator explicitly rejects a pending high-risk shell command",
)
def reject_command(
    request: RejectCommandRequest,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> InspectCommandResponse:
    """Deny and cancel execution of an inspected command flagged for human review."""
    try:
        return service.reject_command(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending command inspection '{request.inspection_id}' not found.",
        ) from err


@router.get(
    "/commands/pending",
    response_model=list[InspectCommandResponse],
    summary="List all shell commands currently awaiting human operator approval",
)
def list_pending_commands(
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> list[InspectCommandResponse]:
    """Retrieve queued high-risk command tickets."""
    return service.list_pending_commands()


@router.post(
    "/snapshots",
    response_model=WorkspaceSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture lightweight Copy-on-Write差异快照 before workspace file edits",
)
def create_snapshot(
    request: CreateSnapshotRequest,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> WorkspaceSnapshotResponse:
    """Record original state and hashes of target files for instant rollback."""
    return service.create_snapshot(request)


@router.post(
    "/snapshots/rollback",
    response_model=WorkspaceSnapshotResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically roll back workspace files to a recorded snapshot state",
)
def rollback_snapshot(
    request: RollbackSnapshotRequest,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> WorkspaceSnapshotResponse:
    """Restore file contents and delete newly created artifacts."""
    try:
        return service.rollback_snapshot(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace snapshot '{request.snapshot_id}' not found.",
        ) from err


@router.get(
    "/snapshots",
    response_model=list[WorkspaceSnapshotResponse],
    summary="List all tracked workspace snapshots",
)
def list_snapshots(
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> list[WorkspaceSnapshotResponse]:
    """Retrieve metadata of all historical workspace snapshots."""
    return service.list_snapshots()


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=WorkspaceSnapshotResponse,
    summary="Retrieve a specific workspace snapshot by ID",
)
def get_snapshot(
    snapshot_id: str,
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> WorkspaceSnapshotResponse:
    """Fetch details of a single snapshot."""
    try:
        return service.get_snapshot(snapshot_id)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace snapshot '{snapshot_id}' not found.",
        ) from err


@router.get(
    "/metrics",
    response_model=HostExecutionGuardMetricsResponse,
    summary="Get cumulative operational metrics for host execution guardrail suite",
)
def get_metrics(
    service: HostExecutionGuardService = Depends(get_host_execution_guard_service),
) -> HostExecutionGuardMetricsResponse:
    """Inspect metrics on inspected paths, redirected paths, blocked commands, and snapshots."""
    return service.get_metrics()
