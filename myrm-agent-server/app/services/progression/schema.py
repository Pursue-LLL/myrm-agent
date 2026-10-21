"""Progression schema and level computation.

[INPUT]
- Persisted milestone map from UserConfig

[OUTPUT]
- Typed progression models and deterministic level derivation

[POS]
Single source of truth for progression milestones and current level rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from pydantic import BaseModel, Field


class MilestoneDef(TypedDict):
    id: str
    label: str
    level: int


MILESTONES: tuple[MilestoneDef, ...] = (
    {"id": "first_chat", "label": "完成第一轮对话", "level": 1},
    {"id": "first_tool_use", "label": "首次完成工具调用", "level": 2},
    {"id": "first_approval", "label": "首次完成审批闭环", "level": 3},
    {"id": "first_remote_takeover", "label": "首次完成远程接管", "level": 4},
    {"id": "first_multistep_delivery", "label": "首次完成多步骤交付", "level": 5},
)


class MilestoneRecord(BaseModel):
    completed_at: datetime | None = None


class ProgressionData(BaseModel):
    current_level: int = Field(default=1, ge=1, le=5)
    milestones: dict[str, MilestoneRecord] = Field(default_factory=dict)


def compute_level_from_milestones(milestones: dict[str, MilestoneRecord]) -> int:
    """Derive the highest unlocked level from completed milestones."""
    highest_level = 1
    for definition in MILESTONES:
        record = milestones.get(definition["id"])
        if record is None or record.completed_at is None:
            continue
        if definition["level"] > highest_level:
            highest_level = definition["level"]
    return highest_level
