"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryRecallScopeBoundary, MemoryFourPartitionSummary, MemoryCandidateRecord, MemoryApprovedRecord, MemoryRecallBoundaryData, MemoryBehavioralInsightsResponse

[POS]
Memory command center schemas: recall scope boundaries, four-partition summary, candidate/approved records and behavioral insights.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemoryRecallScopeBoundary(BaseModel):
    """Single scope boundary specification in review-first recall."""

    level: str
    label: str
    is_active: bool
    namespace_pattern: str
    description: str


class MemoryFourPartitionSummary(BaseModel):
    """Stored memories per job partition (Identity, Session Memory, Operating Instructions, Retrievable Evidence)."""

    identity_count: int = 0
    session_memory_count: int = 0
    operating_instructions_count: int = 0
    retrievable_evidence_count: int = 0


class MemoryCandidateRecord(BaseModel):
    """Candidate memory awaiting user approval or graduation."""

    id: str
    memory_type: str
    content_preview: str
    confidence: float
    source: str
    created_at: datetime
    status: Literal["pending", "review_required"] = "pending"


class MemoryApprovedRecord(BaseModel):
    """Approved/active memory currently participating in task recall."""

    id: str
    memory_type: str
    content_preview: str
    namespace: str
    partition: Literal["identity", "session_memory", "operating_instructions", "retrievable_evidence"]
    importance: float | None = Field(default=None, description="None for a memory type that has no importance score.")
    access_count: int
    is_pinned: bool = False


class MemoryRecallBoundaryData(BaseModel):
    """Complete Review-First Per-Task Memory Recall Boundary snapshot."""

    agent_id: str | None = None
    task_id: str | None = None
    read_scopes: list[MemoryRecallScopeBoundary] = Field(default_factory=list)
    write_policy: str = "inherit"
    partitions: MemoryFourPartitionSummary = Field(default_factory=MemoryFourPartitionSummary)
    candidate_records: list[MemoryCandidateRecord] = Field(default_factory=list)
    approved_records: list[MemoryApprovedRecord] = Field(default_factory=list)
    total_candidates: int = 0
    total_approved: int = 0


class MemoryBehavioralInsightsResponse(BaseModel):
    """Deterministic behavioral routine insights response."""

    hour_histogram: list[int] = Field(default_factory=lambda: [0] * 24)
    workday_hour_histogram: list[int] = Field(default_factory=lambda: [0] * 24)
    weekend_hour_histogram: list[int] = Field(default_factory=lambda: [0] * 24)
    weekday_histogram: list[int] = Field(default_factory=lambda: [0] * 7)
    reply_latency_p50_ms: float | None = None
    reply_latency_p90_ms: float | None = None
    self_message_count: int = 0
    latency_sample_count: int = 0
    channel_distribution: dict[str, int] = Field(default_factory=dict)
    peak_active_window: str | None = None
    workday_peak_window: str | None = None
    weekend_peak_window: str | None = None
    top_collaborators: list[tuple[str, int]] = Field(default_factory=list)
    offset_minutes: int | None = Field(
        default=None,
        description="Explicit or client-detected timezone offset in minutes. None indicates system auto-detection.",
    )
    detected_timezone: str | None = Field(
        default=None,
        description="Detected IANA timezone identifier (e.g. 'Asia/Shanghai', 'America/New_York').",
    )
    locale_anchor: str | None = Field(
        default=None,
        description="Active locale anchor used to preserve cross-turn semantic consistency.",
    )
    source: str = "persisted"
