"""Cron job CRUD REST endpoints.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- cron.schemas (POS: request/response Pydantic models)

[OUTPUT]
- GET / — list all jobs (filter by agent_id, chat_id, enabled)
- GET /{job_id} — get job by id
- POST / — create job
- PUT /{job_id} — update job
- PATCH /{job_id} — partial update job
- DELETE /{job_id} — delete job

[POS]
Cron job CRUD endpoints. Lifecycle action endpoints (duplicate, pause, resume, trigger,
test-delivery, reset-baseline) are located in `actions.py`.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Query

from app.api.cron.schemas import (
    CronJobCreateRequest,
    CronJobPatchRequest,
    CronJobResponse,
    CronJobUpdateRequest,
)
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache

from . import helpers as _h

router = APIRouter()

USER_ID = "default"


@router.get("/", response_model=list[CronJobResponse])
async def list_jobs(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    chat_id: str | None = Query(None, description="Filter by chat ID"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
) -> list[CronJobResponse]:
    mgr = _h._get_manager()
    jobs = await mgr.list_jobs(
        USER_ID, agent_id=agent_id, chat_id=chat_id, enabled=enabled
    )
    return [_h._to_response(j) for j in jobs]


@router.get("/{job_id}", response_model=CronJobResponse)
async def get_job(job_id: str) -> CronJobResponse:
    mgr = _h._get_manager()
    job = await mgr.get_job(job_id, USER_ID)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _h._to_response(job)


@router.post("/", response_model=CronJobResponse, status_code=201)
async def create_job(

    body: CronJobCreateRequest,
    force: bool = Query(False, description="Bypass manual execution verification gate"),
) -> CronJobResponse:
    from app.platform_utils.sandbox.entitlements.entitlement_guard import (
        EntitlementGuardError,
    )

    mgr = _h._get_manager()
    schedule_val = body.schedule
    if body.schedule_type == "cron" and schedule_val:
        parts = schedule_val.strip().split()
        if len(parts) == 6:
            schedule_val = " ".join(parts[1:])
    schedule_expr = _h._parse_schedule(
        body.schedule_type, schedule_val, body.interval_seconds
    )
    _h._validate_workflow_template_binding(
        body.payload.workflow_template_id, body.agent_id
    )
    if not force:
        await _h._enforce_manual_success_prerequisite(body)

    secret_raw, secret_hash = _h._generate_webhook_secret(body.delivery)

    try:
        job = await mgr.create_job(
            user_id=USER_ID,
            name=body.name,
            schedule=schedule_expr,
            payload=body.payload.model_dump(),
            agent_id=body.agent_id,
            schedule_type=body.schedule_type,
            schedule_timezone=body.schedule_timezone,
            delivery=body.delivery.model_dump() if body.delivery else None,
            max_retries=body.max_retries,
            backoff_base_seconds=body.backoff_base_seconds,
            timeout_seconds=body.timeout_seconds,
            chat_id=body.chat_id,
            pinned_chat=body.pinned_chat,
            webhook_delivery_secret=secret_hash,
        )
    except ValueError as exc:
        if isinstance(exc.__cause__, EntitlementGuardError):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_ingress_requirement_cache()
    return _h._to_response(job, webhook_secret_raw=secret_raw)


@router.put("/{job_id}", response_model=CronJobResponse)
async def update_job(job_id: str, body: CronJobUpdateRequest) -> CronJobResponse:
    mgr = _h._get_manager()
    existing = await mgr.get_job(job_id, USER_ID)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    secret_raw, secret_hash = _h._resolve_update_webhook_secret(
        body.delivery, existing.webhook_delivery_secret
    )

    schedule_expr = None
    if body.schedule_type or body.schedule or body.interval_seconds:
        st = body.schedule_type or existing.schedule_type
        sv = body.schedule or existing.schedule
        iv = (
            body.interval_seconds
            if body.interval_seconds is not None
            else (
                int(existing.schedule) if existing.schedule_type == "interval" else None
            )
        )
        schedule_expr = _h._parse_schedule(st, sv, iv)

    tpl_id = (
        body.payload.workflow_template_id
        if body.payload
        else existing.payload.get("workflow_template_id")
    )
    aid = body.agent_id or existing.agent_id
    _h._validate_workflow_template_binding(tpl_id, aid)

    try:
        job = await mgr.update_job(
            job_id=job_id,
            user_id=USER_ID,
            name=body.name,
            schedule=schedule_expr,
            payload=body.payload.model_dump() if body.payload else None,
            agent_id=body.agent_id,
            enabled=body.enabled,
            schedule_type=body.schedule_type,
            schedule_timezone=body.schedule_timezone,
            delivery=body.delivery.model_dump() if body.delivery else None,
            max_retries=body.max_retries,
            backoff_base_seconds=body.backoff_base_seconds,
            timeout_seconds=body.timeout_seconds,
            pinned_chat=body.pinned_chat,
            webhook_delivery_secret=secret_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()
    return _h._to_response(job, webhook_secret_raw=secret_raw)


@router.patch("/{job_id}", response_model=CronJobResponse)
async def patch_job(job_id: str, body: CronJobPatchRequest) -> CronJobResponse:
    mgr = _h._get_manager()
    existing = await mgr.get_job(job_id, USER_ID)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    patch_data = body.model_dump(exclude_unset=True)
    if not patch_data:
        return _h._to_response(existing)

    st = patch_data.get("schedule_type", existing.schedule_type)
    sv = patch_data.get("schedule", existing.schedule)
    iv = patch_data.get("interval_seconds")
    if (
        iv is None
        and existing.schedule_type == "interval"
        and "interval_seconds" not in patch_data
    ):
        try:
            iv = int(existing.schedule)
        except (ValueError, TypeError):
            iv = None

    schedule_expr = None
    if any(k in patch_data for k in ("schedule_type", "schedule", "interval_seconds")):
        schedule_expr = _h._parse_schedule(st, sv, iv)

    tpl_id = (
        body.payload.workflow_template_id
        if body.payload
        else existing.payload.get("workflow_template_id")
    )
    aid = body.agent_id or existing.agent_id
    _h._validate_workflow_template_binding(tpl_id, aid)

    secret_raw, secret_hash = _h._resolve_patch_webhook_secret(
        patch_data, existing.webhook_delivery_secret
    )

    try:
        job = await mgr.update_job(
            job_id=job_id,
            user_id=USER_ID,
            name=patch_data.get("name"),
            schedule=schedule_expr,
            payload=body.payload.model_dump() if body.payload else None,
            agent_id=patch_data.get("agent_id"),
            enabled=patch_data.get("enabled"),
            schedule_type=patch_data.get("schedule_type"),
            schedule_timezone=patch_data.get("schedule_timezone"),
            delivery=body.delivery.model_dump() if body.delivery else None,
            max_retries=patch_data.get("max_retries"),
            backoff_base_seconds=patch_data.get("backoff_base_seconds"),
            timeout_seconds=patch_data.get("timeout_seconds"),
            pinned_chat=cast(bool | None, patch_data.get("pinned_chat")),
            webhook_delivery_secret=secret_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()
    return _h._to_response(job, webhook_secret_raw=secret_raw)


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    mgr = _h._get_manager()
    deleted = await mgr.delete_job(job_id, USER_ID)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()
