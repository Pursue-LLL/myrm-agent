"""[POS]: app/schemas/decontamination.py
[INPUT]: Request and response parameters for memory provenance attestation, quarantine, and rollbacks.
[OUTPUT]: Strongly typed Pydantic models for origin attestation, active quarantine, and snapshot time travel.
"""

from pydantic import BaseModel, Field


class IssueAttestationRequest(BaseModel):
    """Request payload to issue a cryptographic provenance voucher for a memory."""

    memory_id: str = Field(..., description="Target memory identifier")
    source_kind: str = Field(
        default="user_explicit_instruction",
        description="Source classification (user_explicit_instruction, agent_reflection_distill, external_web_scrape, etc.)",
    )
    session_id: str = Field(..., description="Session identifier where memory was generated")
    turn_index: int = Field(default=0, ge=0, description="Turn index within the conversation")
    evidence_snippet: str = Field(default="", description="Verbatim evidence snippet supporting the memory")
    author_identity: str = Field(default="user", description="Author identity or role")


class AttestationResponse(BaseModel):
    """Cryptographic provenance attestation response model."""

    attestation_id: str = Field(..., description="Unique attestation voucher ID")
    memory_id: str = Field(..., description="Target memory ID")
    source_kind: str = Field(..., description="Origin source category")
    session_id: str = Field(..., description="Origin session ID")
    turn_index: int = Field(..., description="Conversation turn index")
    evidence_snippet: str = Field(..., description="Supporting evidence text snippet")
    author_identity: str = Field(..., description="Author identity")
    sha256_signature: str = Field(..., description="HMAC/SHA256 signature guaranteeing authenticity")
    created_at_epoch: float = Field(..., description="Creation epoch timestamp in seconds")


class EvaluateMemoryRequest(BaseModel):
    """Request payload to scan memory content for poisoning patterns."""

    memory_id: str = Field(..., description="Target memory ID")
    content: str = Field(..., description="Raw text content of the candidate memory")
    source_kind: str = Field(default="", description="Optional origin source classification")


class DecontaminationReportResponse(BaseModel):
    """Sanitation evaluation verdict report."""

    memory_id: str = Field(..., description="Evaluated memory ID")
    status: str = Field(..., description="Sanitation status (clean, suspicious, quarantined, expunged)")
    threat_reasons: list[str] = Field(default_factory=list, description="Poisoning indicators detected")
    evaluated_at_epoch: float = Field(..., description="Evaluation epoch timestamp")


class QuarantineMemoryRequest(BaseModel):
    """Request to explicitly quarantine a memory item."""

    memory_id: str = Field(..., description="Target memory ID")
    reason: str = Field(..., description="Quarantine rationale or violation note")


class CreateSnapshotRequest(BaseModel):
    """Request to capture an active memory state snapshot baseline."""

    label: str = Field(..., description="Human-readable checkpoint label")
    active_memory_ids: list[str] = Field(default_factory=list, description="Active memory IDs set")


class SnapshotResponse(BaseModel):
    """Snapshot checkpoint representation."""

    snapshot_id: str = Field(..., description="Unique snapshot ID")
    label: str = Field(..., description="Snapshot label")
    memory_ids: list[str] = Field(default_factory=list, description="Contained memory IDs")
    created_at_epoch: float = Field(..., description="Creation epoch timestamp")


class RollbackRequest(BaseModel):
    """Request to rollback memory state back to a previous snapshot."""

    snapshot_id: str = Field(..., description="Target snapshot checkpoint ID")
    current_memory_ids: list[str] = Field(default_factory=list, description="Currently active memory IDs set")


class RollbackResponse(BaseModel):
    """Rollback execution outcome report."""

    target_id: str = Field(..., description="Target snapshot or session ID rolled back")
    label: str = Field(..., description="Operation label or reason")
    quarantined_count: int = Field(default=0, ge=0, description="Memories quarantined during rollback")
    restored_count: int = Field(default=0, ge=0, description="Baseline memories restored")
    timestamp_epoch: float = Field(..., description="Execution epoch timestamp")


class DecontaminateSessionRequest(BaseModel):
    """Request to purge and quarantine all memories originating from a corrupt session."""

    session_id: str = Field(..., description="Target corrupted session identifier")


class DecontaminateSessionResponse(BaseModel):
    """Result of session-scoped decontamination purge."""

    session_id: str = Field(..., description="Purged session identifier")
    quarantined_count: int = Field(..., description="Number of memories quarantined from this session")


class FilterCleanMemoriesRequest(BaseModel):
    """Request to filter candidate memory IDs through the quarantine barrier."""

    memory_ids: list[str] = Field(default_factory=list, description="Candidate memory IDs to screen")


class FilterCleanMemoriesResponse(BaseModel):
    """Response containing only un-quarantined clean memory IDs."""

    clean_memory_ids: list[str] = Field(default_factory=list, description="Screened clean memory IDs")
