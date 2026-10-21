"""Progression HTTP API endpoints.

[INPUT]
- app.services.progression.service::{get_progression, mark_milestone}
- app.services.progression.schema::MILESTONES

[OUTPUT]
- router: progression read/update endpoints for WebUI

[POS]
Expose user capability progression state and milestone completion updates.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.progression.schema import MILESTONES
from app.services.progression.service import compute_level, get_progression, mark_milestone

router = APIRouter()


class MilestoneStatus(BaseModel):
    id: str
    label: str
    level: str
    completed_at: datetime | None = None


class ProgressionResponse(BaseModel):
    current_level: int
    milestones: list[MilestoneStatus]


class MarkMilestoneResponse(BaseModel):
    current_level: int
    completed_at: datetime | None = None


def _serialize_milestones() -> list[MilestoneStatus]:
    """Build a default milestone list with empty completion state."""
    return [
        MilestoneStatus(
            id=definition["id"],
            label=definition["label"],
            level=f"L{definition['level']}",
            completed_at=None,
        )
        for definition in MILESTONES
    ]


@router.get("", response_model=ProgressionResponse)
async def get_progression_state() -> ProgressionResponse:
    """Return current user progression state."""
    data = await get_progression()
    current_level = compute_level(data)
    milestones = _serialize_milestones()
    milestone_map = {item.id: item for item in milestones}
    for milestone_id, record in data.milestones.items():
        item = milestone_map.get(milestone_id)
        if item is not None:
            item.completed_at = record.completed_at
    return ProgressionResponse(current_level=current_level, milestones=milestones)


@router.patch("/{milestone_id}", response_model=MarkMilestoneResponse)
async def patch_progression_milestone(milestone_id: str) -> MarkMilestoneResponse:
    """Mark a milestone as completed and return level delta."""
    try:
        data = await mark_milestone(milestone_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    record = data.milestones.get(milestone_id)
    return MarkMilestoneResponse(
        current_level=compute_level(data),
        completed_at=record.completed_at if record is not None else None,
    )
