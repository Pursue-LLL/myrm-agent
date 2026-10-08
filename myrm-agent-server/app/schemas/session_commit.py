"""Pydantic schemas for two-phase session commit and memory diff audit.

[INPUT]
- pydantic::{BaseModel, ConfigDict, Field} (POS: validated request and response models)

[OUTPUT]
- SessionArchiveMessageDTO, SessionCommitRequest, SessionCommitResponseDTO: archived messages and the phase-1 commit
- CommitTaskStatusResponseDTO: background commit task status
- MemoryDiffItemDTO, MemoryDiffStatsDTO, MemoryDiffAuditResponseDTO: memory changes caused by a commit

[POS]
API contracts of two-phase session commit, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SessionArchiveMessageDTO(BaseModel):
    """Message item recorded in Phase 1 messages.jsonl."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., description="Message author role: user, assistant, system, tool")
    content: str = Field(..., description="Message text or stringified content")
    tool_calls: list[dict[str, str]] = Field(default_factory=list, description="Tool invocation metadata")
    tool_results: list[dict[str, str]] = Field(default_factory=list, description="Tool response data")
    referenced_uris: list[str] = Field(default_factory=list, description="URIs of files or external sources accessed")
    timestamp: str | None = Field(default=None, description="ISO8601 message timestamp")


class SessionCommitRequest(BaseModel):
    """Request payload to execute Phase 1 synchronous archival and trigger Phase 2 gating."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Active session identifier")
    messages: list[SessionArchiveMessageDTO] = Field(..., min_length=1, description="Messages to archive")
    boundary_kind: str = Field(
        default="target_completed",
        description="Task boundary kind: target_completed, failure_repaired, user_correction, context_compaction, manual",
    )
    metadata: dict[str, str] = Field(default_factory=dict, description="Session context metadata")


class SessionCommitResponseDTO(BaseModel):
    """Immediate response payload upon completing Phase 1 synchronous archival."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    session_id: str
    archive_id: str
    phase1_persisted: bool
    messages_path: str
    phase2_scheduled: bool


class MemoryDiffItemDTO(BaseModel):
    """Individual memory alteration in memory_diff.json."""

    model_config = ConfigDict(extra="forbid")

    change_kind: str
    memory_type: str
    item_id: str
    before_summary: str | None = None
    after_summary: str | None = None
    timestamp: str | None = None


class MemoryDiffStatsDTO(BaseModel):
    """Summary metrics of memory changes."""

    model_config = ConfigDict(extra="forbid")

    total_added: int = 0
    total_updated: int = 0
    total_superseded: int = 0
    total_deleted: int = 0


class MemoryDiffAuditResponseDTO(BaseModel):
    """Structured audit payload mirroring memory_diff.json."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    archive_id: str
    task_id: str
    timestamp: str
    boundary_kind: str
    changes: list[MemoryDiffItemDTO]
    stats: MemoryDiffStatsDTO


class CommitTaskStatusResponseDTO(BaseModel):
    """Status of an asynchronous commit extraction task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    session_id: str
    archive_id: str
    phase: str
    boundary_kind: str
    created_at: str
    completed_at: str | None = None
    error: str | None = None
    message_count: int
    diff_stats: MemoryDiffStatsDTO | None = None
