"""Unified Runs Hub response schemas.

[INPUT]
- None (standalone schemas)

[OUTPUT]
- UnifiedRunResponse: Single run record from any source
- UnifiedRunsListResponse: Paginated list of unified runs

[POS]
Pydantic models for the Unified Runs Hub aggregation API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RunSource = Literal["cron", "kanban", "background"]
RunStatus = Literal["running", "ok", "error", "skipped", "cancelled", "timed_out"]
RunStopReasonCategory = Literal["limit", "cancelled", "error", "other"]


class RunStopReason(BaseModel):
    """Structured reason for why a run stopped."""

    code: str
    category: RunStopReasonCategory
    message: str
    detail: dict[str, object] | None = None


class UnifiedRunResponse(BaseModel):
    """A single unified run record aggregated from any execution source."""

    id: str
    source: RunSource
    status: RunStatus
    title: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
    summary: str | None = None
    output: str | None = None
    metadata: dict[str, object] | None = None
    agent_id: str | None = None
    job_id: str | None = None
    task_id: str | None = None
    has_execution_steps: bool = False
    stop_reason: RunStopReason | None = None


class UnifiedRunsListResponse(BaseModel):
    """Paginated response for the Unified Runs Hub."""

    items: list[UnifiedRunResponse]
    total: int
    offset: int
    limit: int
    has_more: bool
    degraded: bool = False
    failed_sources: list[RunSource] = []
