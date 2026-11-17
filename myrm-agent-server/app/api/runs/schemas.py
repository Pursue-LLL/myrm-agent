"""Unified Runs Hub response schemas.

[INPUT]
- None (standalone schemas)

[OUTPUT]
- UnifiedRunResponse: Single run record from any source
- UnifiedRunsListResponse: Paginated list of unified runs
- CRON_RUN_STATUSES / FAILED_RUN_STATUSES: the statuses a cron run is stored with, and the ones `status=error` selects

[POS]
Pydantic models and status vocabulary for the Unified Runs Hub aggregation API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RunSource = Literal["cron", "kanban", "background"]
RunStatus = Literal["running", "ok", "error", "skipped", "cancelled", "timed_out", "circuit_break"]
RunStopReasonCategory = Literal["limit", "cancelled", "error", "other"]

# The statuses a cron run is stored with; the other statuses belong to the kanban and shell sources.
CRON_RUN_STATUSES: frozenset[RunStatus] = frozenset({"ok", "error", "skipped", "circuit_break"})
# What the failed filter (`status=error`) selects: a run that ended without finishing its work, whichever source ended it.
FAILED_RUN_STATUSES: frozenset[RunStatus] = frozenset({"error", "timed_out", "circuit_break"})


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
