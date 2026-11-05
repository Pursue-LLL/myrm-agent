"""[OUTPUT]
ApplySpecRequest, SpecifyOutcomeResponse, SpecifyAllResponse

[POS]
Kanban spec rewrite schemas. Specify pass outcomes and the apply-spec request body.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ApplySpecRequest(BaseModel):
    """Body for POST /tasks/{task_id}/apply-spec — persists a cached preview."""

    new_title: str | None = None
    new_body: str = Field(..., min_length=1)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SpecifyOutcomeResponse(BaseModel):
    """One Specifier pass result returned to the UI / SDK."""

    task_id: str
    ok: bool
    reason: str = ""
    new_title: str | None = None
    new_body: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    persisted: bool = False


class SpecifyAllResponse(BaseModel):
    """Batch Specify-all result for a board."""

    items: list[SpecifyOutcomeResponse]
    total: int
    persisted: bool
