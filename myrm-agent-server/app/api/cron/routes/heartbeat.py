"""Heartbeat REST endpoints.

Thin delegation to harness heartbeat module.

[INPUT]
- cron.routes.helpers (POS: conversion utilities and manager accessor)
- cron.schemas (POS: heartbeat Pydantic models)
- myrm_agent_harness.toolkits.cron.heartbeat (POS: heartbeat convenience layer)
- myrm_agent_harness.toolkits.cron.types (POS: cron job domain types)
- myrm_agent_harness.toolkits.cron.engine.parser (POS: cron expression parsing and validation)

[OUTPUT]
- GET  /heartbeat/status — current heartbeat state
- POST /heartbeat/enable — enable / update heartbeat (supports interval and cron)
- POST /heartbeat/disable — disable heartbeat

[POS]
Heartbeat REST endpoints. Delegates to harness heartbeat functions.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.cron.engine.parser import (
    describe_schedule,
    validate_cron_expr,
    validate_timezone,
)
from myrm_agent_harness.toolkits.cron.types import CronJob, Schedule, ScheduleKind

from app.api.cron.schemas import HeartbeatEnableRequest, HeartbeatStatusResponse

from . import helpers as _h

router = APIRouter()

USER_ID = "default"


def _job_to_response(job: CronJob, enabled: bool) -> HeartbeatStatusResponse:
    """Build a HeartbeatStatusResponse from a CronJob."""
    sched = job.schedule
    return HeartbeatStatusResponse(
        enabled=enabled,
        interval_ms=sched.interval_ms,
        schedule_kind=sched.kind.value,
        cron_expr=sched.expr if sched.kind == ScheduleKind.CRON else None,
        timezone=sched.tz,
        schedule_description=describe_schedule(sched),
        prompt=job.prompt,
        model=job.model,
        last_run_at=job.last_run_at,
        last_status=job.last_status.value if job.last_status else None,
        next_run_at=job.next_run_at,
        fire_count=job.fire_count,
    )


def _build_schedule_from_request(
    body: HeartbeatEnableRequest,
) -> Schedule | None:
    """Convert request fields to a harness Schedule, or None for interval mode."""
    if body.schedule_kind == "cron":
        if not body.cron_expr:
            raise HTTPException(
                status_code=400,
                detail="cron_expr is required when schedule_kind='cron'",
            )
        if not validate_cron_expr(body.cron_expr):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression: {body.cron_expr}",
            )
        if body.timezone and not validate_timezone(body.timezone):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timezone: {body.timezone}",
            )
        return Schedule(
            kind=ScheduleKind.CRON,
            expr=body.cron_expr,
            tz=body.timezone,
        )
    return None


@router.get("/heartbeat/status", response_model=HeartbeatStatusResponse)
async def heartbeat_status() -> HeartbeatStatusResponse:
    from myrm_agent_harness.toolkits.cron.heartbeat import get_heartbeat_status

    mgr = _h._get_manager()
    status = await get_heartbeat_status(mgr, USER_ID)
    if not status.job:
        return HeartbeatStatusResponse(enabled=False)
    return _job_to_response(status.job, enabled=status.enabled)


@router.post("/heartbeat/enable", response_model=HeartbeatStatusResponse)
async def heartbeat_enable(body: HeartbeatEnableRequest) -> HeartbeatStatusResponse:
    from myrm_agent_harness.toolkits.cron.heartbeat import enable_heartbeat

    mgr = _h._get_manager()
    schedule = _build_schedule_from_request(body)
    try:
        job = await enable_heartbeat(
            mgr,
            USER_ID,
            interval_ms=body.interval_ms,
            schedule=schedule,
            prompt=body.prompt,
            model=body.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _job_to_response(job, enabled=True)


@router.post("/heartbeat/disable", response_model=HeartbeatStatusResponse)
async def heartbeat_disable() -> HeartbeatStatusResponse:
    from myrm_agent_harness.toolkits.cron.heartbeat import (
        disable_heartbeat,
        get_heartbeat_status,
    )

    mgr = _h._get_manager()
    disabled = await disable_heartbeat(mgr, USER_ID)
    if not disabled:
        raise HTTPException(status_code=404, detail="Heartbeat not found")
    status = await get_heartbeat_status(mgr, USER_ID)
    if not status.job:
        return HeartbeatStatusResponse(enabled=False)
    return _job_to_response(status.job, enabled=False)
