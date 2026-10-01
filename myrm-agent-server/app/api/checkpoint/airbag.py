"""Task safety airbag REST endpoints for unattended autonomous runs.

[INPUT]
- app.services.checkpoint.task_airbag_service::get_task_airbag_service (POS: Singleton service managing airbag lifecycle and persistence.)

[OUTPUT]
- airbag_router: APIRouter for arming, inspecting status, rolling back, and dismissing airbags.
- ArmAirbagRequest / ArmAirbagResponse: DTO models for arming airbag.
- AirbagStatusResponse: DTO model for cumulative mutation summary.
- RollbackAirbagRequest / RollbackAirbagResponse: DTO models for triggering time-travel rollback.
- DismissAirbagRequest / DismissAirbagResponse: DTO models for dismissing airbag.

[POS]
Server-layer checkpoint API: REST endpoints for task safety airbag.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.checkpoint.task_airbag_service import get_task_airbag_service

logger = logging.getLogger(__name__)

airbag_router = APIRouter(prefix="/airbag", tags=["checkpoint-airbag"])


class ArmAirbagRequest(BaseModel):
    task_id: str = Field(..., description="Unique task or goal identifier")
    workspace_path: str = Field(..., description="Target workspace directory")


class ArmAirbagResponse(BaseModel):
    success: bool
    task_id: str
    base_snapshot_id: str | None = None
    is_git_repo: bool = False
    message: str | None = None


class AirbagStatusResponse(BaseModel):
    task_id: str
    total_files_changed: int
    modified_files: list[str]
    added_files: list[str]
    deleted_files: list[str]
    external_effects: list[str]
    can_rollback: bool


class RollbackAirbagRequest(BaseModel):
    task_id: str
    workspace_path: str | None = None


class RollbackAirbagResponse(BaseModel):
    success: bool
    task_id: str
    status: Literal["rolled_back", "failed"]


class DismissAirbagRequest(BaseModel):
    task_id: str
    workspace_path: str | None = None


class DismissAirbagResponse(BaseModel):
    success: bool
    task_id: str
    status: Literal["dismissed", "failed"]


@airbag_router.post("/arm", response_model=ArmAirbagResponse)
async def arm_airbag(req: ArmAirbagRequest) -> ArmAirbagResponse:
    """Arm a safety airbag prior to unattended task execution."""
    service = get_task_airbag_service()
    manifest = await service.arm_airbag(req.task_id, req.workspace_path)
    if manifest is None:
        return ArmAirbagResponse(
            success=False,
            task_id=req.task_id,
            message="Failed to capture pre-flight safety baseline",
        )
    return ArmAirbagResponse(
        success=True,
        task_id=manifest.task_id,
        base_snapshot_id=manifest.base_snapshot_id,
        is_git_repo=manifest.is_git_repo,
    )


@airbag_router.get("/{task_id}/status", response_model=AirbagStatusResponse)
async def get_airbag_status(
    task_id: str,
    workspace_path: str | None = Query(None, description="Workspace path for cold hydration"),
) -> AirbagStatusResponse:
    """Retrieve cumulative changes and external effect warnings since task airbag was armed."""
    service = get_task_airbag_service()
    diff = await service.get_airbag_status(task_id, workspace_path)
    if diff is None:
        raise HTTPException(status_code=404, detail=f"No active or persisted airbag found for task: {task_id}")
    return AirbagStatusResponse(
        task_id=diff.task_id,
        total_files_changed=diff.total_files_changed,
        modified_files=diff.modified_files,
        added_files=diff.added_files,
        deleted_files=diff.deleted_files,
        external_effects=diff.external_effects,
        can_rollback=diff.can_rollback,
    )


@airbag_router.post("/rollback", response_model=RollbackAirbagResponse)
async def rollback_airbag(req: RollbackAirbagRequest) -> RollbackAirbagResponse:
    """Trigger atomic time-travel rollback for a task to its pre-flight baseline."""
    service = get_task_airbag_service()
    success = await service.rollback_airbag(req.task_id, req.workspace_path)
    if not success:
        raise HTTPException(status_code=500, detail=f"Time-travel rollback failed for task: {req.task_id}")
    return RollbackAirbagResponse(
        success=True,
        task_id=req.task_id,
        status="rolled_back",
    )


@airbag_router.post("/dismiss", response_model=DismissAirbagResponse)
async def dismiss_airbag(req: DismissAirbagRequest) -> DismissAirbagResponse:
    """Dismiss airbag after user confirms task output is satisfactory."""
    service = get_task_airbag_service()
    success = service.dismiss_airbag(req.task_id, req.workspace_path)
    if not success:
        raise HTTPException(status_code=404, detail=f"Airbag not found for task: {req.task_id}")
    return DismissAirbagResponse(
        success=True,
        task_id=req.task_id,
        status="dismissed",
    )
