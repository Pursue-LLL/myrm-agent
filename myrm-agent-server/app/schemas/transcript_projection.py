"""Schemas for SQLite transcript projection and adoption disambiguation.

[INPUT]
- Pydantic BaseModel, session IDs, message payloads, and transcript entries.

[OUTPUT]
- TranscriptEntryDTO, SessionMessageDTO, BootstrapSessionRequestDTO,
  BootstrapSessionResponseDTO, AdoptionDecisionDTO.

[POS]
- Server-side DTO contracts for Item 150 SqliteTranscriptProjectionSuite.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptEntryDTO(BaseModel):
    """Raw transcript entry recorded in the SQLite SSOT table."""

    entry_id: str = Field(..., description="Unique transcript entry ID")
    session_id: str = Field(..., description="Session identifier")
    seq: int = Field(..., description="Sequence number in transcript")
    role: str = Field(..., description="Message role: user, assistant, system, tool")
    content: str = Field(..., description="Text content of entry")
    created_at_ms: int | None = Field(default=None, description="Epoch millisecond timestamp")
    parent_id: str | None = Field(default=None, description="Parent entry ID")


class SessionMessageDTO(BaseModel):
    """Working session message row projected from transcript or ingested live."""

    message_id: str = Field(..., description="Unique message identifier")
    session_id: str = Field(..., description="Session identifier")
    seq: int = Field(..., description="Message sequence order")
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp_ms: int | None = Field(default=None, description="Message timestamp in milliseconds")
    transcript_entry_id: str | None = Field(default=None, description="Associated transcript entry ID")


class AdoptionDecisionDTO(BaseModel):
    """Decision outcome mapping a message to a transcript entry."""

    message_id: str
    transcript_entry_id: str | None
    status: str
    reason: str


class BootstrapSessionRequestDTO(BaseModel):
    """Request payload to initiate cold-start transcript projection bootstrap."""

    session_id: str = Field(..., description="Session ID to bootstrap")
    session_key: str = Field(..., description="Full session key")
    agent_id: str = Field(default="main", description="Target agent identifier")
    tolerance_ms: int = Field(default=2000, description="Timestamp tolerance window in milliseconds")


class BootstrapSessionResponseDTO(BaseModel):
    """Response containing result of cold-start bootstrap projection."""

    session_id: str
    bootstrapped: bool
    imported_messages: int
    already_bootstrapped: bool
    decisions: list[AdoptionDecisionDTO]
