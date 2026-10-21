"""Workspace organize HITL API.

[INPUT]
- app.services.files.organize.apply::apply_organize_plan (POS: workspace organize 批量执行与回滚)
- app.services.files.organize.job_store::get_latest_job_for_workspace (POS: organize job 持久化)
- app.core.utils.response_utils::success_response (POS: 统一 JSON 成功响应)

[OUTPUT]
- POST /organize/apply?dryRun= — validate or apply organize plan
- POST /organize/rollback/{job_id} — rollback applied job
- GET /organize/latest-job?workspace= — latest rollbackable job

[POS]
Workspace organize HITL HTTP 层。Agent/skill 生成 plan JSON；用户在 WebUI 审阅后调用 apply/rollback。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.services.files.organize.apply import apply_organize_plan, rollback_organize_job
from app.services.files.organize.job_store import get_latest_job_for_workspace
from app.services.files.organize.types import OrganizePlan

logger = logging.getLogger(__name__)

router = APIRouter()


class OrganizeApplyRequest(BaseModel):
    workspace: str = Field(..., min_length=1)
    plan: OrganizePlan


@router.post("/organize/apply", response_model=None)
async def organize_apply(
    body: OrganizeApplyRequest,
    dry_run: bool = Query(False, alias="dryRun"),
) -> JSONResponse:
    """Validate and optionally apply an organize plan. dryRun=true returns preview only."""
    result = apply_organize_plan(body.workspace, body.plan, dry_run=dry_run)
    if result.issues:
        return success_response(
            data={
                "dryRun": dry_run,
                "ok": False,
                "issues": [issue.model_dump() for issue in result.issues],
            }
        )
    return success_response(
        data={
            "dryRun": result.dry_run,
            "ok": True,
            "jobId": result.job_id,
            "appliedCount": result.applied_count,
            "moves": [move.model_dump() for move in result.moves],
        }
    )


@router.post("/organize/rollback/{job_id}", response_model=None)
async def organize_rollback(job_id: str) -> JSONResponse:
    """Rollback a previously applied organize job."""
    result = rollback_organize_job(job_id)
    return success_response(
        data={
            "jobId": result.job_id,
            "jobStatus": result.job_status.value if result.job_status else None,
            "appliedCount": result.applied_count,
            "moves": [move.model_dump() for move in result.moves],
        }
    )


@router.get("/organize/latest-job", response_model=None)
async def organize_latest_job(workspace: str = Query(..., min_length=1)) -> JSONResponse:
    """Return the latest rollbackable job for a workspace (toast rollback CTA)."""
    job = get_latest_job_for_workspace(workspace)
    if job is None:
        return success_response(data={"job": None})
    return success_response(
        data={
            "job": {
                "jobId": job.job_id,
                "status": job.status.value,
                "appliedCount": len(job.moves),
                "createdAt": job.created_at,
            }
        }
    )
