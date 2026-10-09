"""Schemas and DTOs for Tool-Noise-Free Memory Extraction and Purge Generation Epoch Suite.

[INPUT]
- External: pydantic, datetime, typing

[OUTPUT]
- CleanDialogueRequestDTO / ResponseDTO
- InspectPIIRequestDTO / ResponseDTO
- CommitFactRequestDTO / ResponseDTO
- PurgeMemoryRequestDTO / ResponseDTO
- EpochStatusResponseDTO

[POS]
Server data transfer objects for Topic 01 Item 88 (Anthropic Commerce Agents-style memory isolation,
PII regex screening, and monotonic purge generation fencing).
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurnDTO(BaseModel):
    """Single turn of conversational history."""

    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_calls: list[dict[str, str]] | None = None
    tool_call_id: str | None = None


class CleanDialogueRequestDTO(BaseModel):
    """Request to strip tools and prepare clean extraction context."""

    user_id: str = Field(default="default_user", description="Target user identifier")
    turns: list[ConversationTurnDTO] = Field(description="Conversation turn history")


class CleanDialogueResponseDTO(BaseModel):
    """Response containing clean transcript and observed generation epoch."""

    user_id: str
    clean_transcript: str
    observed_generation: int
    tokens_saved: int
    stripped_turns_count: int


class PIIViolationDetailDTO(BaseModel):
    """Details of a single blocked PII violation."""

    rule_name: str
    snippet_masked: str
    severity: str


class InspectPIIRequestDTO(BaseModel):
    """Request to inspect statement against PII regex gateway."""

    statement: str = Field(description="Candidate text to inspect")
    mask_instead_of_reject: bool = Field(default=False, description="Whether to mask sensitive tokens")


class InspectPIIResponseDTO(BaseModel):
    """Result of PII inspection."""

    is_clean: bool
    sanitized_text: str
    violations: list[PIIViolationDetailDTO] = Field(default_factory=list)


class ExtractedFactCandidateDTO(BaseModel):
    """Fact statement candidate ready for persistence."""

    fact_id: str
    fact_text: str
    category: str = "user_preference"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    generation_observed: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommitFactRequestDTO(BaseModel):
    """Request to validate and commit an extracted fact candidate."""

    user_id: str = Field(default="default_user", description="Target user identifier")
    candidate: ExtractedFactCandidateDTO


class CommitFactResponseDTO(BaseModel):
    """Response indicating whether the candidate passed epoch fence and PII screening."""

    success: bool
    message: str
    violation: PIIViolationDetailDTO | None = None


class PurgeMemoryRequestDTO(BaseModel):
    """Request to clear memory and advance purge generation epoch."""

    user_id: str = Field(default="default_user", description="Target user identifier")


class PurgeMemoryResponseDTO(BaseModel):
    """Response confirming purge and generation advance."""

    user_id: str
    new_generation: int
    purged_facts_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EpochStatusResponseDTO(BaseModel):
    """Status record of a user's purge generation and epoch fencing health."""

    user_id: str
    current_generation: int
    active_extractions: int = 0
    stale_writes_dropped: int = 0
    last_purged_at: str | None = None
    stored_facts_count: int = 0
    pii_violations_blocked: int = 0
