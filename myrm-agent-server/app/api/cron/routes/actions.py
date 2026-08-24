"""Cron job lifecycle actions REST endpoints.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- cron.schemas (POS: request/response Pydantic models)

[OUTPUT]
- POST /{job_id}/duplicate — duplicate job with config, paused
- POST /{job_id}/pause — pause job
- POST /{job_id}/resume — resume job
- POST /{job_id}/trigger — trigger immediate execution
- POST /{job_id}/test-delivery — send test delivery payload
- POST /{job_id}/reset-baseline — reset monitor baseline

[POS]
Cron job operation endpoints. All business logic delegated to CronManager.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.cron.schemas import (
    CronJobResponse,
    DeliveryTestRequest,
    DeliveryTestResponse,
)
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache

from . import helpers as _h

router = APIRouter()

USER_ID = "default"


@router.post("/{job_id}/duplicate", response_model=CronJobResponse, status_code=201)
async def duplicate_job(job_id: str) -> CronJobResponse:
    from app.platform_utils.sandbox.entitlements.entitlement_guard import (
        EntitlementGuardError,
    )

    mgr = _h._get_manager()
    try:
        job = await mgr.duplicate_job(job_id, USER_ID)
    except ValueError as exc:
        if isinstance(exc.__cause__, EntitlementGuardError):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()
    return _h._to_response(job)


@router.post("/{job_id}/pause", response_model=CronJobResponse)
async def pause_job(job_id: str) -> CronJobResponse:
    mgr = _h._get_manager()
    job = await mgr.pause_job(job_id, USER_ID)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _h._to_response(job)


@router.post("/{job_id}/resume", response_model=CronJobResponse)
async def resume_job(job_id: str) -> CronJobResponse:
    mgr = _h._get_manager()
    try:
        job = await mgr.resume_job(job_id, USER_ID)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _h._to_response(job)


@router.post("/{job_id}/trigger", status_code=202)
async def trigger_job(job_id: str) -> dict[str, bool]:
    mgr = _h._get_manager()
    triggered = await mgr.trigger_now(job_id, USER_ID)
    if not triggered:
        raise HTTPException(status_code=404, detail="Job not found or not active")
    return {"triggered": True}


@router.post("/{job_id}/test-delivery", response_model=DeliveryTestResponse)
async def test_delivery(
    job_id: str,
    body: DeliveryTestRequest | None = None,
) -> DeliveryTestResponse:
    """Send a one-off test payload through the job's delivery channel."""
    mgr = _h._get_manager()
    return await _h._run_test_delivery(mgr, job_id, body)


@router.post("/{job_id}/reset-baseline")
async def reset_baseline(job_id: str) -> dict[str, bool]:
    mgr = _h._get_manager()
    reset = await mgr.reset_monitor_baseline(job_id, USER_ID)
    if not reset:
        raise HTTPException(
            status_code=404, detail="Job not found or no monitor baseline"
        )
    return {"reset": True}
