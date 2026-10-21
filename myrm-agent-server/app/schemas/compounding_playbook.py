"""Compounding playbook status schemas.

[INPUT]
- (none)

[OUTPUT]
- CompoundingPlaybookStatusResponse and related DTOs

[POS]
Pydantic schemas for compounding playbook status API responses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CompoundingChecklistId = Literal["memory", "skills", "cron", "verify"]


class CompoundingChecklistItem(BaseModel):
    id: CompoundingChecklistId
    ready: bool
    count: int = Field(ge=0)
    deep_link: str


class CompoundingPlaybookStatusResponse(BaseModel):
    agent_id: str | None = None
    items: list[CompoundingChecklistItem]
    ready_count: int = Field(ge=0)
    total_count: int = Field(default=4, ge=1)
