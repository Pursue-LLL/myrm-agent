"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandConflictItem, MemoryCommandReplayOverlay, MemoryCommandReplayEvent, MemoryCommandWaterfallStep, MemoryCommandTraceStep, MemoryCommandTraceRun

[POS]
Memory command center schemas: conflict replay, trace runs and the turn waterfall.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemoryCommandConflictItem(BaseModel):
    """Claim, correction, supersession, and pending-conflict visibility item."""

    id: str
    kind: Literal["claim", "correction", "supersession", "pending_conflict"]
    status: Literal["pending", "active", "needs_review", "resolved"]
    memory_id: str | None = None
    related_memory_id: str | None = None
    title: str
    description: str
    existing_content: str | None = None
    candidate_content: str | None = None
    created_at: datetime | None = None


class MemoryCommandReplayOverlay(BaseModel):
    """Session replay overlay index for memory events."""

    chat_id: str
    message_id: str | None = None
    event_count: int
    influence_count: int
    last_event_at: datetime
    last_summary: str


class MemoryCommandReplayEvent(BaseModel):
    """One normalized event for the replay timeline."""

    id: str
    phase: Literal["observe", "govern", "write", "index", "recall", "inject", "verify"]
    status: str
    occurred_at: datetime
    title: str
    summary: str
    target_kind: str | None = None
    target_id: str | None = None
    correlation_id: str | None = None
    influence_count: int = 0


class MemoryCommandWaterfallStep(BaseModel):
    """Aggregated memory operation waterfall step."""

    phase: Literal[
        "observe",
        "scan",
        "propose",
        "approve",
        "write",
        "index",
        "recall",
        "inject",
        "cite",
        "verify",
    ]
    status: Literal["ready", "active", "warning", "missing"]
    event_count: int = 0
    evidence_count: int = 0
    latest_at: datetime | None = None
    description: str


class MemoryCommandTraceStep(BaseModel):
    """One persisted retrieval trace step within a memory recall run."""

    id: str
    phase: str
    status: Literal["success", "warning", "error", "skipped"]
    title: str
    description: str
    occurred_at: datetime
    duration_ms: float | None = None
    output_count: int = 0
    result_count: int = 0
    step_index: int = 0


class MemoryCommandTraceRun(BaseModel):
    """A grouped memory retrieval trace run for the command center UI."""

    id: str
    trace_id: str
    message_id: str | None = None
    chat_id: str | None = None
    query_preview: str = ""
    status: Literal["success", "warning", "error", "skipped"]
    occurred_at: datetime
    duration_ms: float | None = None
    result_count: int = 0
    steps: list[MemoryCommandTraceStep] = Field(default_factory=list)
