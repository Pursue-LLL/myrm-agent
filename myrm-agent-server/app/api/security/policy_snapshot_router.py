"""API router for In-Flight Policy Snapshot Pinning & Non-Silent Drift.

[INPUT]
- BindTaskPolicyRequest, SoftUpdatePolicyRequest, EmergencyHotKillRequest,
  RevokeEmergencyHotKillRequest, AssertToolExecutionRequest.

[OUTPUT]
- Endpoints for task policy snapshot pinning, dual-track updates, and tool assertions.

[POS]
- Server API. Mounted under /api/v1/security/policy-snapshot.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.policy_snapshot import (
    AssertToolExecutionRequest,
    AssertToolExecutionResponse,
    BindTaskPolicyRequest,
    EmergencyHotKillDirectiveDto,
    EmergencyHotKillRequest,
    ExecutionPolicySnapshotDto,
    RevokeEmergencyHotKillRequest,
    SoftUpdatePolicyRequest,
)
from app.services.security.policy_snapshot_service import (
    get_policy_snapshot_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/policy-snapshot", tags=["policy-snapshot"])


@router.get("/active", response_model=ExecutionPolicySnapshotDto)
def get_active_policy_snapshot() -> ExecutionPolicySnapshotDto:
    """Retrieve the currently active policy snapshot for new tasks."""
    service = get_policy_snapshot_service()
    return service.get_active_snapshot()


@router.post("/bind", response_model=ExecutionPolicySnapshotDto, status_code=status.HTTP_201_CREATED)
def bind_task_policy(req: BindTaskPolicyRequest) -> ExecutionPolicySnapshotDto:
    """Pin the current active policy snapshot to an in-flight task."""
    service = get_policy_snapshot_service()
    return service.bind_task_policy(req.task_id)


@router.get("/tasks/{task_id}", response_model=ExecutionPolicySnapshotDto)
def get_task_pinned_policy(task_id: str) -> ExecutionPolicySnapshotDto:
    """Retrieve the pinned policy snapshot for an in-flight task."""
    service = get_policy_snapshot_service()
    snapshot = service.get_task_policy(task_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' has no pinned policy snapshot",
        )
    return snapshot


@router.post("/soft-update", response_model=ExecutionPolicySnapshotDto)
def apply_soft_update(req: SoftUpdatePolicyRequest) -> ExecutionPolicySnapshotDto:
    """Apply Track A Soft Update: new policy takes effect for future tasks without affecting in-flight."""
    service = get_policy_snapshot_service()
    return service.apply_soft_update(req)


@router.post(
    "/emergency-hot-kill",
    response_model=EmergencyHotKillDirectiveDto,
    status_code=status.HTTP_201_CREATED,
)
def apply_emergency_hot_kill(req: EmergencyHotKillRequest) -> EmergencyHotKillDirectiveDto:
    """Apply Track B Emergency Hot Kill: immediately blocks high-risk tools across in-flight tasks."""
    service = get_policy_snapshot_service()
    return service.apply_emergency_hot_kill(req)


@router.post("/revoke-emergency-hot-kill")
def revoke_emergency_hot_kill(req: RevokeEmergencyHotKillRequest) -> dict[str, bool]:
    """Revoke an active emergency hot-kill directive."""
    service = get_policy_snapshot_service()
    success = service.revoke_emergency_hot_kill(req.directive_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directive '{req.directive_id}' not found or already inactive",
        )
    return {"revoked": True}


@router.post("/assert-tool", response_model=AssertToolExecutionResponse)
def assert_tool_execution(req: AssertToolExecutionRequest) -> AssertToolExecutionResponse:
    """Assert whether a tool call is permitted for an in-flight task under its pinned policy."""
    service = get_policy_snapshot_service()
    return service.assert_tool_execution(task_id=req.task_id, tool_name=req.tool_name)
