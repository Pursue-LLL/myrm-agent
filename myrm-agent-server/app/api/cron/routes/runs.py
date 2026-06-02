"""Cron run history REST endpoints.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- cron.schemas (POS: run response Pydantic models)

[OUTPUT]
- GET /{job_id}/runs — runs for a specific job (paginated)
- GET /runs/all — all runs across jobs (paginated)

[POS]
Cron run history REST endpoints. Read-only views of execution records.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.cron.schemas import CronRunsListResponse

from . import helpers as _h

router = APIRouter()

USER_ID = "default"


@router.get("/{job_id}/runs", response_model=CronRunsListResponse)
async def list_job_runs(
    job_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
) -> CronRunsListResponse:
    mgr = _h._get_manager()
    runs = await mgr.list_runs(USER_ID, job_id=job_id, limit=limit, offset=offset, status=status)
    total = await mgr.count_runs(USER_ID, job_id=job_id, status=status)

    job = await mgr.get_job(job_id, USER_ID)
    job_name = job.name if job else None

    return CronRunsListResponse(
        items=[_h._run_to_response(r, job_name=job_name) for r in runs],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + limit < total,
    )


@router.get("/runs/all", response_model=CronRunsListResponse)
async def list_all_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
) -> CronRunsListResponse:
    mgr = _h._get_manager()
    runs = await mgr.list_runs(USER_ID, limit=limit, offset=offset, status=status)
    total = await mgr.count_runs(USER_ID, status=status)

    job_ids = list({r.job_id for r in runs})
    all_jobs = await mgr.list_jobs(USER_ID) if job_ids else []
    job_names = {j.id: j.name for j in all_jobs if j.id in set(job_ids)}

    return CronRunsListResponse(
        items=[_h._run_to_response(r, job_name=job_names.get(r.job_id)) for r in runs],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + limit < total,
    )
