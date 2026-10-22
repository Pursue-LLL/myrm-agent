"""Pydantic V2 schemas for Lightweight Fusen Shared State Sync (Item 63).

[INPUT]
- PostFusenNoteRequest, ResolveFusenNoteRequest.

[OUTPUT]
- FusenNoteDTO, FusenBlockerSummaryDTO.

[POS]
- Server-side DTO layer for Item 63 Fusen shared sticky-note protocol.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class FusenCategoryDTOEnum(enum.StrEnum):
    """Categorization of lightweight state sticky notes."""

    BLOCKER = "blocker"
    READY_FOR_REVIEW = "ready_for_review"
    CACHE_HINT = "cache_hint"
    IN_PROGRESS = "in_progress"
    CUSTOM = "custom"


class NoteStatusDTOEnum(enum.StrEnum):
    """Lifecycle status of a Fusen sticky note."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class FusenNoteDTO(BaseModel):
    """Immutable data transfer object representing a Fusen sticky note."""

    model_config = ConfigDict(frozen=True)

    note_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    author_agent_id: str = Field(..., min_length=1)
    category: FusenCategoryDTOEnum = Field(...)
    tag: str = Field(..., min_length=1)
    content: str = Field(default="")
    metadata: dict[str, str] = Field(default_factory=dict)
    status: NoteStatusDTOEnum = Field(default=NoteStatusDTOEnum.ACTIVE)
    resolution_note: str | None = Field(default=None)
    ttl_seconds: float | None = Field(default=None)
    created_at: float = Field(default=0.0)
    updated_at: float = Field(default=0.0)


class PostFusenNoteRequest(BaseModel):
    """Payload to post a new lightweight state sticky note."""

    model_config = ConfigDict(frozen=True)

    note_id: str | None = Field(default=None, description="Optional custom unique note ID")
    session_id: str = Field(..., min_length=1, description="Associated agent team session ID")
    author_agent_id: str = Field(..., min_length=1, description="Agent ID posting this sticky note")
    category: FusenCategoryDTOEnum = Field(default=FusenCategoryDTOEnum.CUSTOM)
    tag: str = Field(..., min_length=1, description="Structured tag (e.g. 'blocked_by: tool_x')")
    content: str = Field(default="", description="Optional human-readable or structured details")
    metadata: dict[str, str] | None = Field(default=None, description="Optional metadata key-values")
    ttl_seconds: float | None = Field(default=None, ge=1.0, description="Optional TTL in seconds")


class ResolveFusenNoteRequest(BaseModel):
    """Payload to resolve an active sticky note."""

    model_config = ConfigDict(frozen=True)

    resolution_note: str = Field(default="", description="Explanation or evidence of resolution")


class FusenBlockerSummaryDTO(BaseModel):
    """DTO summarizing active blockers affecting an agent team."""

    model_config = ConfigDict(frozen=True)

    is_blocked: bool = Field(...)
    blocker_count: int = Field(...)
    blockers: list[FusenNoteDTO] = Field(default_factory=list)
    active_tags: list[str] = Field(default_factory=list)
