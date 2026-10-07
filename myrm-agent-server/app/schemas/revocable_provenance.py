"""[POS]: app/schemas/revocable_provenance.py
[INPUT]: Pydantic BaseModel, Field, datetime, and typing primitives.
[OUTPUT]: Request and response DTO schemas for provenance-qualified memories, atomic forget results, and dream diaries.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProvenanceMetadataDTO(BaseModel):
    """Source chat turn linkage anchoring memory to raw transcript."""

    session_id: str = Field(description="Source chat session ID")
    message_id: str = Field(description="Exact message ID where fact was spoken")
    turn_index: int = Field(ge=0, description="Turn index within the conversation")
    quote_snippet: str = Field(description="Verbatim quote snippet supporting the memory")
    extracted_at: datetime = Field(description="Timestamp when fact was distilled")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")


class ProvenanceQualifiedMemoryDTO(BaseModel):
    """Promoted long-term memory asset with full origin traceability."""

    memory_id: str = Field(description="Unique memory identifier")
    statement: str = Field(description="Distilled memory fact statement")
    category: str = Field(description="Memory category or domain tag")
    provenance: ProvenanceMetadataDTO = Field(description="Origin source turn metadata")
    is_revoked: bool = Field(description="True if memory was revoked by user or system")
    revoked_at: datetime | None = Field(default=None, description="Timestamp of revocation")
    revocation_reason: str = Field(default="", description="Reason for revocation")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class SaveProvenanceMemoryRequestDTO(BaseModel):
    """Payload to record a new provenance-qualified memory entry."""

    memory_id: str | None = Field(default=None, description="Optional custom memory ID")
    statement: str = Field(description="Distilled actionable statement or preference")
    category: str = Field(default="general_preference", description="Domain category")
    session_id: str = Field(description="Origin session identifier")
    message_id: str = Field(description="Origin message identifier")
    turn_index: int = Field(default=0, ge=0, description="Conversation turn index")
    quote_snippet: str = Field(description="Verbatim conversation snippet supporting fact")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")


class ForgetMemoryRequestDTO(BaseModel):
    """Payload to atomically revoke a memory while keeping source transcripts intact."""

    reason: str = Field(default="", description="Reason or correction note for revocation")


class ForgetResultDTO(BaseModel):
    """Outcome report of atomic memory revocation."""

    memory_id: str = Field(description="Revoked memory ID")
    revoked: bool = Field(description="True if revocation was processed")
    source_session_id: str = Field(description="Origin session ID")
    source_message_id: str = Field(description="Origin message ID")
    message: str = Field(description="Outcome description")
    transcript_intact: bool = Field(default=True, description="True guaranteeing raw transcript integrity")


class DreamDiaryEntryDTO(BaseModel):
    """Transparent diary log capturing background memory distillation cycles."""

    dream_id: str = Field(description="Unique dream cycle ID")
    agent_id: str = Field(description="Target agent ID")
    scanned_turns: int = Field(ge=0, description="Count of scanned transcript turns")
    promoted_memory_ids: list[str] = Field(default_factory=list, description="IDs of memories promoted")
    pruned_duplicates_count: int = Field(ge=0, description="Count of duplicate or stale items pruned")
    duration_ms: float = Field(ge=0.0, description="Consolidation duration in milliseconds")
    status: str = Field(description="Execution status: completed, skipped, failed")
    notes: str = Field(default="", description="Synthesis notes or highlights")
    created_at: datetime = Field(description="Log timestamp")


class RecordDreamDiaryRequestDTO(BaseModel):
    """Request payload to log a completed dreaming consolidation cycle."""

    agent_id: str = Field(description="Target agent ID")
    scanned_turns: int = Field(ge=0, description="Count of scanned turns")
    promoted_memory_ids: list[str] | None = Field(default=None, description="Promoted memory IDs")
    pruned_duplicates_count: int = Field(default=0, ge=0, description="Count of pruned items")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds")
    status: str = Field(default="completed", description="Cycle status")
    notes: str = Field(default="", description="Synthesis notes")
