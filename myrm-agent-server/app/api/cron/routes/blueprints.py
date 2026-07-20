"""Cron blueprint API endpoints.

Exposes the server-defined blueprint catalog and fill logic,
enabling both the frontend and Agent tool to consume identical definitions.

[INPUT]
- core.cron.blueprints (POS: Blueprint definitions single source of truth)

[OUTPUT]
- GET /blueprints — list all available blueprints
- POST /blueprints/fill — fill a blueprint with slot values, return schedule + prompt + job defaults

[POS]
Blueprint catalog and fill API for cron automation templates.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
    BlueprintFillError,
    BlueprintSlot,
    fill_blueprint,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SlotResponse(BaseModel):
    name: str
    type: str
    label: str
    default: str
    options: list[str] = Field(default_factory=list)
    optional: bool = False


class BlueprintResponse(BaseModel):
    id: str
    icon: str
    title: dict[str, str]
    description: dict[str, str]
    prompt_template: dict[str, str]
    slots: list[SlotResponse]
    category: str
    tags: list[str]
    sort_order: int


class BlueprintFillRequest(BaseModel):
    blueprint_id: str
    values: dict[str, str] = Field(default_factory=dict)
    locale: str = "en"
    tz: str | None = None


class ScheduleResultResponse(BaseModel):
    kind: str
    expr: str | None = None
    tz: str | None = None
    interval_ms: int | None = None


class MonitorConfigPresetResponse(BaseModel):
    monitor_type: str
    ttl_days: int
    enabled: bool


class FailureAlertPresetResponse(BaseModel):
    enabled: bool
    after: int
    cooldown_seconds: int


class BlueprintFillResponse(BaseModel):
    schedule: ScheduleResultResponse
    prompt: str
    name: str
    required_capabilities: list[str] = Field(default_factory=list)
    tools_allowed: list[str] = Field(default_factory=list)
    job_type: str = "agent"
    session_target: str = "isolated"
    deduplicate: bool = False
    skip_if_active: bool = False
    timeout_seconds: int | None = None
    monitor_config: MonitorConfigPresetResponse | None = None
    failure_alert: FailureAlertPresetResponse | None = None
    pre_condition_script: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _slot_to_response(slot: BlueprintSlot) -> SlotResponse:
    return SlotResponse(
        name=slot.name,
        type=slot.type,
        label=slot.label,
        default=slot.default,
        options=list(slot.options),
        optional=slot.optional,
    )


@router.get("/blueprints", response_model=list[BlueprintResponse])
async def list_blueprints() -> list[BlueprintResponse]:
    """Return all available automation blueprints."""
    return [
        BlueprintResponse(
            id=bp.id,
            icon=bp.icon,
            title=bp.title,
            description=bp.description,
            prompt_template=bp.prompt_template,
            slots=[_slot_to_response(s) for s in bp.slots],
            category=bp.category,
            tags=list(bp.tags),
            sort_order=bp.sort_order,
        )
        for bp in BUILTIN_BLUEPRINTS
    ]


@router.post("/blueprints/fill", response_model=BlueprintFillResponse)
async def fill_blueprint_endpoint(body: BlueprintFillRequest) -> BlueprintFillResponse:
    """Fill a blueprint with slot values, returning ready-to-use schedule and prompt."""
    try:
        result = fill_blueprint(
            body.blueprint_id,
            body.values,
            locale=body.locale,
            tz=body.tz,
        )
    except BlueprintFillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail=f"Blueprint '{body.blueprint_id}' not found")

    return BlueprintFillResponse(
        schedule=ScheduleResultResponse(
            kind=result.schedule.kind,
            expr=result.schedule.expr,
            tz=result.schedule.tz,
            interval_ms=result.schedule.interval_ms,
        ),
        prompt=result.prompt,
        name=result.name,
        required_capabilities=list(result.required_capabilities),
        tools_allowed=list(result.tools_allowed) if result.tools_allowed else [],
        job_type=result.job_type,
        session_target=result.session_target,
        deduplicate=result.deduplicate,
        skip_if_active=result.skip_if_active,
        timeout_seconds=result.timeout_seconds,
        monitor_config=(
            MonitorConfigPresetResponse(
                monitor_type=result.monitor_config.monitor_type,
                ttl_days=result.monitor_config.ttl_days,
                enabled=result.monitor_config.enabled,
            )
            if result.monitor_config
            else None
        ),
        failure_alert=(
            FailureAlertPresetResponse(
                enabled=result.failure_alert.enabled,
                after=result.failure_alert.after,
                cooldown_seconds=result.failure_alert.cooldown_seconds,
            )
            if result.failure_alert
            else None
        ),
        pre_condition_script=result.pre_condition_script,
    )
