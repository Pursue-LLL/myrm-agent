"""BatchDirectory API request/response schemas.

[INPUT]
pydantic::BaseModel/Field (POS: 数据模型基座)

[OUTPUT]
BatchProjectCreate/BatchProjectResponse/BatchProjectListResponse 等 API 请求响应模型

[POS] Pydantic models for batch-directory API endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BatchProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    prompt: str = Field(..., min_length=1)
    directories: list[str] = Field(..., min_length=1)
    board_id: str | None = Field(
        None,
        max_length=32,
        description="Existing board to place tasks in; auto-creates a dedicated board when omitted.",
    )
    concurrency: int = Field(3, ge=1, le=50)
    agent_id: str | None = Field(None, max_length=255)
    model_override: str | None = Field(None, max_length=255)
    max_runtime_seconds: int | None = Field(None, ge=1)
    require_approval: bool = False
    notify_enabled: bool = True
    artifact_patterns: list[str] | None = None


class BatchTaskItem(BaseModel):
    task_id: str
    title: str
    status: str
    workspace_path: str | None = None
    agent_id: str | None = None
    result: str = ""
    error: str = ""
    created_at: str | None = None
    completed_at: str | None = None


class BatchProjectResponse(BaseModel):
    project_id: str
    name: str
    prompt: str
    board_id: str | None = None
    status: str
    concurrency: int
    agent_id: str | None = None
    model_override: str | None = None
    max_runtime_seconds: int | None = None
    require_approval: bool = False
    notify_enabled: bool = True
    directories: list[str] = Field(default_factory=list)
    artifact_patterns: list[str] = Field(default_factory=list)
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class BatchProjectDetailResponse(BatchProjectResponse):
    tasks: list[BatchTaskItem] = Field(default_factory=list)
    created_task_ids: list[str] = Field(default_factory=list)
    failed_directories: list[str] = Field(default_factory=list)
    cancelled_task_ids: list[str] = Field(default_factory=list)


class BatchProjectListResponse(BaseModel):
    items: list[BatchProjectResponse] = Field(default_factory=list)
    total: int = 0
