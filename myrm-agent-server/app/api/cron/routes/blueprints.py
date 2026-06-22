"""Cron blueprint API endpoints.

Exposes the server-defined blueprint catalog and fill logic,
enabling both the frontend and Agent tool to consume identical definitions.

[INPUT]
- core.cron.blueprints (POS: Blueprint definitions single source of truth)

[OUTPUT]
- GET /blueprints — list all available blueprints
- POST /blueprints/fill — fill a blueprint with slot values, return schedule + prompt

[POS]
Blueprint catalog and fill API for cron automation templates.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
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


class BlueprintFillResponse(BaseModel):
    schedule: ScheduleResultResponse
    prompt: str
    name: str


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
    result = fill_blueprint(
        body.blueprint_id,
        body.values,
        locale=body.locale,
        tz=body.tz,
    )
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
    )
