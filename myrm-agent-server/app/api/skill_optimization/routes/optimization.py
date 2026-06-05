from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization import (
    OptimizationRepository,
    QualityRepository,
)
from app.api.skill_optimization.dependencies import (
    get_scheduler,
)
from app.database.connection import get_db

router = APIRouter()


class OptimizeTriggerRequest(BaseModel):
    """手动触发优化请求"""

    force: bool = False


class FeedbackRequest(BaseModel):
    """用户反馈请求"""

    feedback_type: str
    comment: str | None = None


@router.post("/optimize/{skill_id}")
async def trigger_optimization(
    skill_id: str,
    request: OptimizeTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """手动触发skill优化"""
    quality_repo = QualityRepository(db)
    opt_repo = OptimizationRepository(db)

    latest_quality = await quality_repo.get_latest_quality(skill_id)

    if not latest_quality and not request.force:
        raise HTTPException(
            status_code=404,
            detail=f"No quality data found for skill {skill_id}. Use force=true to proceed.",
        )

    baseline_score = latest_quality.quality_score if latest_quality else {}

    record = await opt_repo.create(
        skill_id=skill_id,
        skill_type="USER",
        baseline_score=baseline_score,
        skill_version=1,
    )

    return {"message": f"Optimization triggered for {skill_id}", "record_id": record.id}


@router.post("/feedback/{skill_id}")
async def submit_feedback(skill_id: str, request: FeedbackRequest) -> dict[str, object]:
    """提交用户反馈"""
    return {
        "message": "Feedback submitted",
        "skill_id": skill_id,
        "feedback_type": request.feedback_type,
    }


@router.get("/batch-status/{batch_task_id}")
async def get_batch_optimization_status(
    batch_task_id: str,
    scheduler: Annotated[OptimizationScheduler, Depends(get_scheduler)],
) -> dict[str, object]:
    """获取批量优化任务状态

    查询批量任务进度（S3扩展）。
    """
    status = scheduler.get_batch_status(batch_task_id)

    if status is None:
        raise HTTPException(status_code=404, detail=f"Batch task not found: {batch_task_id}")

    return cast(dict[str, object], status)
