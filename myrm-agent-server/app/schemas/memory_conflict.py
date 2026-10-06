"""
[POS] app/schemas/memory_conflict.py
[INPUT] pydantic
[OUTPUT] EvaluateConflictRequestDTO, EvaluateConflictResponseDTO, PendingConflictItemDTO, PendingConflictListResponseDTO, HumanArbitrateRequestDTO, HumanArbitrateResponseDTO, FreezeLockStatusResponseDTO, UnlockDecisionRequestDTO, UnlockDecisionResponseDTO

Pydantic DTOs for working memory conflict semantic arbitration and user-confirmed decision freeze gate.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluateConflictRequestDTO(BaseModel):
    """Payload to request semantic conflict evaluation between existing and candidate facts."""

    model_config = ConfigDict(extra="forbid")

    entity_key: str = Field(..., description="Key or identifier of target entity (e.g. database_choice)")
    attribute_name: str = Field(..., description="Target attribute name (e.g. engine)")
    existing_memory_id: str = Field(..., description="ID of existing stored memory")
    existing_fact_text: str = Field(..., description="Content of existing memory fact")
    candidate_fact_text: str = Field(..., description="Candidate incoming fact content")
    source_context: str = Field(default="", description="Originating conversation or document context")
    auto_stage_if_disputed: bool = Field(
        default=True,
        description="Whether to automatically stage unresolved contradictions into pending arbitration queue",
    )


class EvaluateConflictResponseDTO(BaseModel):
    """Result of semantic conflict evaluation."""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(..., description="Unique conflict evaluation ID")
    resolution_kind: str = Field(..., description="Resolution kind: merge, override, contradiction, freeze_blocked")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Arbitration confidence score")
    reasoning: str = Field(..., description="Explanation of why this resolution was assessed")
    suggested_text: str = Field(..., description="Suggested merged or preserved fact content")
    requires_human_confirmation: bool = Field(..., description="Whether human confirmation card is required")
    is_staged_in_pending: bool = Field(..., description="Whether staged in pending arbitration store")


class PendingConflictItemDTO(BaseModel):
    """Individual conflict pending human review."""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(..., description="Unique conflict ID")
    entity_key: str = Field(..., description="Target entity key")
    attribute_name: str = Field(..., description="Target attribute name")
    existing_memory_id: str = Field(..., description="Existing memory record ID")
    existing_fact_text: str = Field(..., description="Existing recorded fact")
    candidate_fact_text: str = Field(..., description="Candidate new fact text")
    severity: str = Field(..., description="Severity level: low, medium, high, critical")
    detected_at: str = Field(..., description="ISO 8601 timestamp of detection")
    source_context: str = Field(default="", description="Context string")
    is_existing_frozen: bool = Field(..., description="Whether existing memory is currently freeze-locked")


class PendingConflictListResponseDTO(BaseModel):
    """List of all conflicts currently awaiting human arbitration."""

    model_config = ConfigDict(extra="forbid")

    total_count: int = Field(..., ge=0, description="Total number of pending conflict items")
    items: list[PendingConflictItemDTO] = Field(..., description="Pending conflict records")


class HumanArbitrateRequestDTO(BaseModel):
    """Payload submitted by human operator to finalize a conflict decision."""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(..., description="Target conflict ID to finalize")
    chosen_resolution: str = Field(..., description="Chosen resolution: merge, override, contradiction")
    final_fact_text: str = Field(..., description="Final approved fact text")
    operator_id: str = Field(..., description="ID of operator/user who made the decision")
    should_freeze_lock: bool = Field(
        default=True,
        description="Whether to place an immutable freeze lock on this finalized decision",
    )
    comment: str = Field(default="", description="Optional operator comment or reason")


class HumanArbitrateResponseDTO(BaseModel):
    """Result returned after applying human arbitration decision."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether arbitration was successfully finalized")
    conflict_id: str = Field(..., description="Finalized conflict ID")
    final_fact_text: str = Field(..., description="Final approved content")
    is_frozen: bool = Field(..., description="Whether freeze lock is actively guarding the record")
    immutable_hash: str | None = Field(default=None, description="Cryptographic SHA-256 lock hash")
    message: str = Field(..., description="Human-readable result summary")


class FreezeLockStatusResponseDTO(BaseModel):
    """Status details of a user-confirmed freeze lock."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Memory ID queried")
    is_frozen: bool = Field(..., description="Whether memory is actively freeze-locked")
    frozen_content: str | None = Field(default=None, description="Frozen fact text if locked")
    confirmed_by: str | None = Field(default=None, description="Operator identifier who confirmed the lock")
    confirmed_at: str | None = Field(default=None, description="ISO timestamp when lock was created")
    immutable_hash: str | None = Field(default=None, description="Cryptographic lock hash")
    lock_version: int = Field(default=1, ge=1, description="Current lock version")
    integrity_valid: bool = Field(..., description="Whether hash matches internal payload")


class UnlockDecisionRequestDTO(BaseModel):
    """Payload to explicitly release a user-confirmed freeze lock."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Memory record ID to unlock")
    operator_id: str = Field(..., description="Operator requesting the unlock")
    reason: str = Field(..., description="Architectural or operational justification for unlocking")


class UnlockDecisionResponseDTO(BaseModel):
    """Outcome of unlock request."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether lock was deactivated")
    memory_id: str = Field(..., description="Target memory ID")
    message: str = Field(..., description="Status explanation")
