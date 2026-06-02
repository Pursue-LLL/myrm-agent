from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.media.batch.orchestrator import batch_orchestrator
from app.database.models import BatchImageJob

"""Batch image generation API — create, control, monitor batch jobs."""

logger = logging.getLogger(__name__)
router = APIRouter()


class BatchPlanItemInput(BaseModel):
    prompt: str
    model: str | None = None
    size: str | None = None
    quality: str | None = None


class CreateBatchJobRequest(BaseModel):
    items: list[BatchPlanItemInput] = Field(..., min_length=1, max_length=50)
    concurrency: int = Field(default=3, ge=1, le=10)
    session_id: str | None = None


class BatchJobResponse(BaseModel):
    id: str
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    plan: list[dict[str, object]] | None = None
    concurrency: int
    estimated_cost: str | None = None
    session_id: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


def _to_response(job: "BatchImageJob") -> BatchJobResponse:

    return BatchJobResponse(
        id=job.id,
        status=job.status,
        total_items=job.total_items,
        completed_items=job.completed_items,
        failed_items=job.failed_items,
        plan=job.plan,
        concurrency=job.concurrency,
        estimated_cost=job.estimated_cost,
        session_id=job.session_id,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


@router.post("", response_model=BatchJobResponse)
async def create_batch_job(
    body: CreateBatchJobRequest,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Create a new batch image generation job."""
    items = [item.model_dump() for item in body.items]
    job = await batch_orchestrator.create_job(
        db,
        items=items,
        concurrency=body.concurrency,
        session_id=body.session_id,
    )
    await db.commit()
    return _to_response(job)


@router.post("/{job_id}/start", response_model=BatchJobResponse)
async def start_batch_job(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Start executing a batch job."""
    try:
        job = await batch_orchestrator.start_job(db, job_id)
        return _to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{job_id}/pause", response_model=BatchJobResponse)
async def pause_batch_job(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Pause a running batch job."""
    try:
        job = await batch_orchestrator.pause_job(db, job_id)
        await db.commit()
        return _to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{job_id}/resume", response_model=BatchJobResponse)
async def resume_batch_job(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Resume a paused batch job."""
    try:
        job = await batch_orchestrator.resume_job(db, job_id)
        await db.commit()
        return _to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{job_id}/cancel", response_model=BatchJobResponse)
async def cancel_batch_job(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Cancel a batch job."""
    try:
        job = await batch_orchestrator.cancel_job(db, job_id)
        await db.commit()
        return _to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{job_id}/retry", response_model=BatchJobResponse)
async def retry_failed_items(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Retry failed items in a batch job."""
    try:
        job = await batch_orchestrator.retry_failed(db, job_id)
        return _to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{job_id}", response_model=BatchJobResponse)
async def get_batch_job(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BatchJobResponse:
    """Get batch job status and details."""
    try:
        job = await batch_orchestrator.get_job(db, job_id)
        return _to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
