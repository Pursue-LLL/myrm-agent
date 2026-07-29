"""Pydantic schemas for Second Brain onboarding preset."""

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
