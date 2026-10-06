"""API router for Immutable Host Sandbox and Zero Blast Radius Rollback Suite.

[POS] app/api/security/immutable_sandbox_rollback_router.py
[INPUT] app/schemas/immutable_sandbox_rollback.py, app/services/security/immutable_sandbox_rollback_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.immutable_sandbox_rollback import (
    CheckpointResponse,
    CreateCheckpointRequest,
    EvaluateCommandBlastRadiusRequest,
    EvaluateCommandBlastRadiusResponse,
    GetMountSpecRequest,
    GetMountSpecResponse,
    ListCheckpointsResponse,
    RollbackRequest,
    RollbackResponse,
)
from app.services.security.immutable_sandbox_rollback_service import (
    ImmutableSandboxRollbackService,
    get_immutable_sandbox_rollback_service,
)

router = APIRouter(prefix="/immutable-sandbox", tags=["immutable-sandbox-rollback"])


@router.post("/evaluate-command", response_model=EvaluateCommandBlastRadiusResponse)
async def evaluate_command_blast_radius(
    req: EvaluateCommandBlastRadiusRequest,
    service: ImmutableSandboxRollbackService = Depends(get_immutable_sandbox_rollback_service),
) -> EvaluateCommandBlastRadiusResponse:
    """Pre-execution assessment of shell command blast radius against immutable OS boundaries."""
    return service.evaluate_command_blast_radius(req)


@router.post("/mount-spec", response_model=GetMountSpecResponse)
async def get_sandbox_mount_spec(
    req: GetMountSpecRequest,
    service: ImmutableSandboxRollbackService = Depends(get_immutable_sandbox_rollback_service),
) -> GetMountSpecResponse:
    """Generate hardened read-only root and bind-mount specifications with Docker CLI flags."""
    return service.get_mount_spec(req)


@router.post("/checkpoints/create", response_model=CheckpointResponse)
async def create_sandbox_checkpoint(
    req: CreateCheckpointRequest,
    service: ImmutableSandboxRollbackService = Depends(get_immutable_sandbox_rollback_service),
) -> CheckpointResponse:
    """Create an atomic snapshot checkpoint for a sandbox environment."""
    return service.create_checkpoint(req)


@router.post("/checkpoints/rollback", response_model=RollbackResponse)
async def rollback_sandbox_checkpoint(
    req: RollbackRequest,
    service: ImmutableSandboxRollbackService = Depends(get_immutable_sandbox_rollback_service),
) -> RollbackResponse:
    """Execute atomic zero-cost environment rollback to a prior checkpoint."""
    return service.rollback_to_checkpoint(req)


@router.get("/checkpoints/{sandbox_id}", response_model=ListCheckpointsResponse)
async def list_sandbox_checkpoints(
    sandbox_id: str,
    service: ImmutableSandboxRollbackService = Depends(get_immutable_sandbox_rollback_service),
) -> ListCheckpointsResponse:
    """List all snapshots registered for a sandbox."""
    return service.list_checkpoints(sandbox_id)
