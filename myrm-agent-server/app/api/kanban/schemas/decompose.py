"""[OUTPUT]
DecomposeChildResponse, DecomposeOutcomeResponse, ApplyDecomposeRequest

[POS]
Kanban decompose schemas. Decompose child proposals and the apply-decompose request body.
"""

from __future__ import annotations

from pydantic import BaseModel


class DecomposeChildResponse(BaseModel):
    """One proposed child task in a decompose preview."""

    title: str
    body: str
    assignee: str | None = None
    parent_indices: list[int] = []
    extra_skill_ids: list[str] = []


class DecomposeOutcomeResponse(BaseModel):
    """One Decomposer pass result returned to the UI."""

    task_id: str
    ok: bool
    fanout: bool = False
    children: list[DecomposeChildResponse] = []
    rationale: str = ""
    reason: str = ""
    new_title: str | None = None
    new_body: str | None = None
    new_assignee: str | None = None
    child_ids: list[str] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    persisted: bool = False


class ApplyDecomposeRequest(BaseModel):
    """Body for POST /tasks/{task_id}/apply-decompose."""

    fanout: bool = True
    children: list[DecomposeChildResponse] = []
    new_title: str | None = None
    new_body: str | None = None
    new_assignee: str | None = None
    rationale: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
