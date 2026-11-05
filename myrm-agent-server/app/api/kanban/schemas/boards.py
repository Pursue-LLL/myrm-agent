"""[OUTPUT]
BoardCreate, BoardUpdate, BoardResponse, AgentTaskCounts, BoardSummaryResponse, BoardListResponse

[POS]
Kanban board CRUD schemas. Board create/update/response models and the board summary aggregation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BoardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    project_id: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Optional project scope for this board.",
    )
    milestone_id: str | None = Field(
        None,
        min_length=1,
        max_length=32,
        description="Optional milestone scope for this board.",
    )
    max_concurrent_tasks: int = Field(3, ge=1, le=50)
    heartbeat_interval_seconds: int = Field(30, ge=10, le=600)
    zombie_timeout_seconds: int = Field(120, ge=30, le=1800)
    max_retries_per_task: int = Field(3, ge=0, le=20)
    auto_block_after_consecutive_failures: int = Field(5, ge=1, le=50)
    specify_max_tokens: int = Field(6000, ge=1500, le=32000)
    auto_specify_on_create: bool = False
    default_workdir: str | None = Field(
        None,
        max_length=1024,
        description="Default workspace directory for tasks on this board.",
    )
    block_recurrence_limit: int = Field(
        2,
        ge=1,
        le=50,
        description="How many block/unblock cycles escalate a task to TRIAGE.",
    )


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    max_concurrent_tasks: int | None = Field(None, ge=1, le=50)
    specify_max_tokens: int | None = Field(None, ge=1500, le=32000)
    auto_specify_on_create: bool | None = None
    default_workdir: str | None = Field(
        None,
        max_length=1024,
        description="Default workspace directory for tasks on this board.",
    )
    block_recurrence_limit: int | None = Field(
        None,
        ge=1,
        le=50,
        description="How many block/unblock cycles escalate a task to TRIAGE.",
    )


class BoardResponse(BaseModel):
    board_id: str
    name: str
    description: str
    settings: dict[str, int | bool | str | None]
    created_at: datetime
    updated_at: datetime


class AgentTaskCounts(BaseModel):
    """Per-agent task distribution (non-archived only)."""

    agent_id: str | None = None
    counts: dict[str, int] = {}
    total: int = 0


class BoardSummaryResponse(BaseModel):
    board: BoardResponse
    task_counts: dict[str, int]
    total_tasks: int
    dispatcher_active: bool = False
    by_agent: list[AgentTaskCounts] = []
    oldest_ready_age_seconds: int | None = None
    stale_running_count: int = 0


class BoardListResponse(BaseModel):
    items: list[BoardResponse]
    total: int
