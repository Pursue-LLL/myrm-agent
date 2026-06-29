"""Scheduler health endpoint.

Exposes the harness CronScheduler's internal health metrics to the frontend
so users can verify their automation engine is alive at a glance.

[INPUT]
- cron.routes.helpers (POS: scheduler accessor)
- myrm_agent_harness.toolkits.cron.engine.scheduler (POS: CronScheduler.health())

[OUTPUT]
- GET /scheduler/health — scheduler liveness status (green/yellow/red)

[POS]
Scheduler health endpoint. Delegates to harness CronScheduler.health().
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from . import helpers as _h

router = APIRouter()


class SchedulerHealthResponse(BaseModel):
    status: Literal["green", "yellow", "red"]
    running: bool
    last_tick_at: str | None = None
    tick_errors: int = 0
    last_tick_age_seconds: float | None = None
    has_timer: bool = False


@router.get("/scheduler/health", response_model=SchedulerHealthResponse)
async def scheduler_health() -> SchedulerHealthResponse:
    scheduler = _h._get_scheduler()
    raw = scheduler.health()

    running: bool = raw.get("running", False)
    last_tick_at: str | None = raw.get("last_tick_at")
    tick_errors: int = raw.get("tick_errors", 0)
    has_timer: bool = raw.get("has_timer", False)

    age: float | None = None
    if last_tick_at:
        try:
            last_dt = datetime.fromisoformat(last_tick_at)
            age = (datetime.now(UTC) - last_dt).total_seconds()
        except (ValueError, TypeError):
            pass

    if not running or last_tick_at is None:
        status: Literal["green", "yellow", "red"] = "red"
    elif (age is not None and age > 120) or tick_errors > 0:
        status = "yellow"
    else:
        status = "green"

    return SchedulerHealthResponse(
        status=status,
        running=running,
        last_tick_at=last_tick_at,
        tick_errors=tick_errors,
        last_tick_age_seconds=round(age, 1) if age is not None else None,
        has_timer=has_timer,
    )
