"""[INPUT]
- pydantic BaseModel / Field (POS: 请求/响应模型基类)

[OUTPUT]
PlanRevisionItemRequest, PlanRevisionRequest, PlanRevisionResponse

[POS]
Kanban plan revision schemas. Atomic DAG plan revision request/response.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanRevisionItemRequest(BaseModel):
    """A single task change in a plan revision."""

    action: str = Field(..., description="'add', 'update', or 'remove'")
    task_id: str | None = None
    title: str | None = None
    description: str | None = None
    priority: str = "normal"
    agent_id: str | None = None
    model_override: str | None = None
    extra_skill_ids: list[str] = []
    depends_on: list[str] = []


class PlanRevisionRequest(BaseModel):
    """Request body for atomic DAG plan revision."""

    board_id: str
    rationale: str = Field(..., min_length=1, description="Reason for plan revision")
    task_changes: list[PlanRevisionItemRequest] = []
    add_edges: list[list[str]] = []
    remove_edges: list[list[str]] = []
    author: str = "user"


class PlanRevisionResponse(BaseModel):
    """Response returned after plan revision."""

    ok: bool
    board_id: str
    reason: str
    added_task_ids: list[str] = []
    updated_task_ids: list[str] = []
    removed_task_ids: list[str] = []
    added_edges: list[list[str]] = []
    removed_edges: list[list[str]] = []
    persisted: bool = False
