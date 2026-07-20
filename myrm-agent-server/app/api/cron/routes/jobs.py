"""Cron job CRUD REST endpoints.

Thin delegation layer: parameter parsing → CronManager → response conversion.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- cron.schemas (POS: request/response Pydantic models)

[OUTPUT]
- GET /  — list jobs (paginated)
- POST / — create job
- GET /{job_id} — get single job
- PATCH /{job_id} — update job
- DELETE /{job_id} — delete job
- POST /{job_id}/duplicate — duplicate job with config, paused
- POST /{job_id}/pause — pause job
- POST /{job_id}/resume — resume job
- POST /{job_id}/trigger — trigger immediate execution
- POST /{job_id}/reset-baseline — reset monitor baseline

[POS]
Cron job CRUD REST endpoints. All business logic delegated to CronManager.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.cron.schemas import (
    CronJobCreate,
    CronJobResponse,
    CronJobsListResponse,
    CronJobUpdate,
)
from app.core.cron.adapters.tools_policy import normalize_cron_tools_allowed
from app.core.infra.ingress_requirement import invalidate_ingress_requirement_cache

from . import helpers as _h

router = APIRouter()

USER_ID = "default"


@router.get("/", response_model=CronJobsListResponse)
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=200),
    chat_id: str | None = Query(None, max_length=255),
) -> CronJobsListResponse:
    mgr = _h._get_manager()
    name_filter = search.strip() if search else None
    chat_filter = chat_id.strip() if chat_id else None
    jobs = await mgr.list_jobs(
        USER_ID,
        name_filter=name_filter,
        chat_id=chat_filter,
        limit=limit,
        offset=offset,
    )
    if name_filter or chat_filter:
        all_matched = await mgr.list_jobs(
            USER_ID,
            name_filter=name_filter,
            chat_id=chat_filter,
        )
        total = len(all_matched)
    else:
        total = await mgr.count_jobs(USER_ID)

    job_ids = [j.id for j in jobs if j.monitor_config]
    monitor_states = await mgr.batch_get_monitor_states(job_ids) if job_ids else {}

    return CronJobsListResponse(
        items=[_h._to_response(j, monitor_states.get(j.id)) for j in jobs],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + limit < total,
    )


@router.post("/", response_model=CronJobResponse, status_code=201)
async def create_job(body: CronJobCreate) -> CronJobResponse:
    from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError

    mgr = _h._get_manager()
    try:
        tools_allowed = normalize_cron_tools_allowed(body.tools_allowed)
        job = await mgr.create_job(
            user_id=USER_ID,
            name=body.name,
            job_type=body.job_type,
            schedule=_h._build_schedule(body.schedule),
            prompt=body.prompt,
            model=body.model,
            chat_id=body.chat_id,
            agent_id=body.agent_id,
            command=body.command,
            delivery=_h._delivery_from_request(body.delivery),
            failure_delivery=_h._delivery_from_request(body.failure_delivery) if body.failure_delivery else None,
            failure_alert=_h._failure_alert_from_request(body.failure_alert),
            active_hours=_h._active_hours_from_request(body.active_hours),
            required_capabilities=tuple(body.required_capabilities) if body.required_capabilities else (),
            tools_allowed=tools_allowed,
            allowed_roots=tuple(body.allowed_roots) if body.allowed_roots else (),
            triggers=_h._trigger_config_from_request(body.triggers),
            max_retries=body.max_retries,
            retry_backoff_ms=body.retry_backoff_ms,
            timeout_seconds=body.timeout_seconds,
            misfire_grace_seconds=body.misfire_grace_seconds,
            cooldown_seconds=body.cooldown_seconds,
            max_fires=body.max_fires,
            expires_at=body.expires_at,
            session_target=body.session_target,
            delete_after_run=body.delete_after_run,
            run_retention_days=body.run_retention_days,
            deduplicate=body.deduplicate,
            monitor_config=_h._monitor_config_from_request(body.monitor_config),
            context_from=tuple(body.context_from) if body.context_from else (),
            pre_condition_script=body.pre_condition_script,
        )
    except ValueError as e:
        if isinstance(e.__cause__, EntitlementGuardError):
            raise HTTPException(status_code=403, detail=str(e)) from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    invalidate_ingress_requirement_cache()
    return _h._to_response(job)


@router.get("/{job_id}", response_model=CronJobResponse)
async def get_job(job_id: str) -> CronJobResponse:
    mgr = _h._get_manager()
    job = await mgr.get_job(job_id, USER_ID)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    state = await mgr.get_monitor_state(job_id) if job.monitor_config else None
    return _h._to_response(job, state)


@router.patch("/{job_id}", response_model=CronJobResponse)
async def update_job(job_id: str, body: CronJobUpdate) -> CronJobResponse:
    from myrm_agent_harness.toolkits.cron.types import CronJobPatch

    mgr = _h._get_manager()
    try:
        tools_allowed: tuple[str, ...] | None = None
        clear_tools_allowed = False
        if "tools_allowed" in body.model_fields_set:
            if body.tools_allowed:
                tools_allowed = normalize_cron_tools_allowed(body.tools_allowed)
            else:
                clear_tools_allowed = True
        patch = CronJobPatch(
            name=body.name,
            status=body.status,
            schedule=_h._build_schedule(body.schedule) if body.schedule else None,
            prompt=body.prompt,
            model=body.model,
            agent_id=body.agent_id,
            command=body.command,
            delivery=_h._delivery_from_request(body.delivery) if body.delivery else None,
            failure_delivery=_h._delivery_from_request(body.failure_delivery) if body.failure_delivery else None,
            clear_failure_delivery=body.failure_delivery is None and "failure_delivery" in body.model_fields_set,
            failure_alert=_h._failure_alert_from_request(body.failure_alert) if body.failure_alert is not None else None,
            clear_failure_alert=body.failure_alert is None and "failure_alert" in body.model_fields_set,
            active_hours=_h._active_hours_from_request(body.active_hours) if body.active_hours else None,
            clear_active_hours=body.active_hours is None and "active_hours" in body.model_fields_set,
            required_capabilities=tuple(body.required_capabilities) if body.required_capabilities is not None else None,
            tools_allowed=tools_allowed,
            clear_tools_allowed=clear_tools_allowed,
            allowed_roots=tuple(body.allowed_roots) if body.allowed_roots is not None else None,
            triggers=_h._trigger_config_from_request(body.triggers) if body.triggers else None,
            clear_triggers=body.triggers is None and "triggers" in body.model_fields_set,
            max_retries=body.max_retries,
            retry_backoff_ms=body.retry_backoff_ms,
            timeout_seconds=body.timeout_seconds,
            misfire_grace_seconds=body.misfire_grace_seconds,
            cooldown_seconds=body.cooldown_seconds,
            max_fires=body.max_fires,
            clear_max_fires=body.max_fires is None and "max_fires" in body.model_fields_set,
            expires_at=body.expires_at,
            clear_expires_at=body.expires_at is None and "expires_at" in body.model_fields_set,
            session_target=body.session_target,
            chat_id=body.chat_id,
            clear_chat_id=body.chat_id is None and "chat_id" in body.model_fields_set,
            delete_after_run=body.delete_after_run,
            run_retention_days=body.run_retention_days,
            deduplicate=body.deduplicate,
            monitor_config=_h._monitor_config_from_request(body.monitor_config) if body.monitor_config else None,
            clear_monitor_config=body.monitor_config is None and "monitor_config" in body.model_fields_set,
            context_from=tuple(body.context_from) if body.context_from is not None else None,
            clear_context_from=body.context_from is None
            and "context_from" in body.model_fields_set
            or (body.context_from is not None and len(body.context_from) == 0),
            pre_condition_script=body.pre_condition_script,
            clear_pre_condition_script=body.pre_condition_script is None and "pre_condition_script" in body.model_fields_set,
        )
        job = await mgr.update_job(job_id, USER_ID, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()
    return _h._to_response(job)


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    mgr = _h._get_manager()
    deleted = await mgr.delete_job(job_id, USER_ID)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    invalidate_ingress_requirement_cache()


@router.post("/{job_id}/duplicate", response_model=CronJobResponse, status_code=201)
async def duplicate_job(job_id: str) -> CronJobResponse:
    from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError

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
    job = await mgr.resume_job(job_id, USER_ID)
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


@router.post("/{job_id}/reset-baseline")
async def reset_baseline(job_id: str) -> dict[str, bool]:
    mgr = _h._get_manager()
    reset = await mgr.reset_monitor_baseline(job_id, USER_ID)
    if not reset:
        raise HTTPException(status_code=404, detail="Job not found or no monitor baseline")
    return {"reset": True}
