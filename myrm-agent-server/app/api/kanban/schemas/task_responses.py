"""[INPUT]
- pydantic BaseModel / Field (POS: 请求/响应模型基类)

[OUTPUT]
AttachmentInfo, TaskResponse, TaskListResponse, ReclaimResponse, RunResponse, EventResponse, RunListResponse, EventListResponse, BoardEventResponse, BoardEventListResponse

[POS]
Kanban task/run/event response schemas. Read models for a task, its runs, events and the reclaim outcome.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .diagnostics import DiagnosticSummaryResponse


class AttachmentInfo(BaseModel):
    """Resolved attachment metadata for display."""

    file_id: str
    filename: str
    content_type: str
    url: str


class TaskResponse(BaseModel):
    task_id: str
    board_id: str
    title: str
    description: str
    status: str
    priority: str
    agent_id: str | None = None
    model_override: str | None = None
    parent_task_id: str | None = None
    workspace_path: str | None = None
    branch: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    consecutive_failures: int = 0
    blocked_reason: str | None = None
    block_kind: str | None = None
    scheduled_until: datetime | None = None
    progress_note: str | None = None
    result: str = ""
    error: str = ""
    metadata: dict[str, object] = {}
    extra_skill_ids: list[str] = []
    attachment_ids: list[str] = []
    attachments: list[AttachmentInfo] = []
    max_runtime_seconds: int | None = None
    goal_mode: bool = False
    goal_max_turns: int | None = None
    require_approval: bool = False
    completion_criteria: str | list[dict[str, str | int]] | None = None
    dep_count: int = 0
    children_total: int = 0
    children_done: int = 0
    comment_count: int = 0
    diagnostics_summary: DiagnosticSummaryResponse | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


class ReclaimResponse(BaseModel):
    """Response for a reclaim operation."""

    reclaimed: bool
    task: TaskResponse | None = None


class RunResponse(BaseModel):
    run_id: str
    task_id: str
    worker_id: str
    started_at: datetime
    ended_at: datetime | None = None
    outcome: str | None = None
    summary: str = ""
    error: str = ""
    duration_seconds: float | None = None
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None


class EventResponse(BaseModel):
    event_id: int
    task_id: str
    kind: str
    payload: dict[str, object] | None = None
    run_id: str | None = None
    created_at: datetime


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int


class BoardEventResponse(BaseModel):
    event_id: int
    task_id: str
    task_title: str = ""
    task_assignee: str = ""
    kind: str
    payload: dict[str, object] | None = None
    run_id: str | None = None
    created_at: str


class BoardEventListResponse(BaseModel):
    items: list[BoardEventResponse]
    total: int
