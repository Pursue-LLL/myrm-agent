"""Pydantic schemas for Second Brain onboarding preset.

[INPUT]
- None (self-contained schema definitions)

[OUTPUT]
- ChecklistItem: 4-item readiness checklist item model
- SecondBrainPresetState: persistent state for preset application
- SecondBrainApplyResponse: API response after applying preset
- SecondBrainStatusResponse: API response for preset status query

[POS]
Pure data models extracted from second_brain_preset for line-budget compliance.
No business logic; consumed by second_brain_preset.py and API layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_ORIGIN = "second_brain_preset"


class ChecklistItem(BaseModel):
    id: Literal["agent_tools", "cron_job", "vault_content", "provider_ready"]
    ready: bool


class SecondBrainPresetState(BaseModel):
    agent_id: str | None = None
    agent_name: str | None = None
    cron_job_id: str | None = None
    applied_at: str | None = None
    origin: str = _ORIGIN


class SecondBrainApplyResponse(BaseModel):
    success: bool
    message: str
    agent_id: str
    agent_name: str
    cron_job_id: str | None
    checklist: list[ChecklistItem]
    applied_at: str


class SecondBrainStatusResponse(BaseModel):
    applied: bool
    agent_id: str | None = None
    agent_name: str | None = None
    cron_job_id: str | None = None
    applied_at: str | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list)
