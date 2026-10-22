"""[INPUT] Pydantic models for Hermes Fabric remote dispatch durable journal REST APIs.
[OUTPUT] Strong DTOs: WorkContractDTO, DispatchReceiptDTO, PrestartRevalidateRequest, PrestartRevalidateResponse, EvidenceSubmitRequest, EvidenceSubmitResponse, JournalEntryDTO, RecoveryPlanDTO.
[POS] Public schema models for durable remote dispatch subsystem.
"""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field


class WorkContractDTO(BaseModel):
    """Execution contract governing a deterministic remote dispatch task."""

    dispatch_id: str = Field(default_factory=lambda: f"dsp_{uuid.uuid4().hex[:10]}", description="Unique dispatch ID")
    task_name: str = Field(..., description="Designated subtask identifier")
    target_peer_id: str = Field(..., description="Target worker node or sandbox ID")
    coordinator_principal_id: str = Field(default="coord_primary", description="Authoritative coordinator principal")
    max_budget_tokens: int = Field(default=50000, description="Token allowance for remote worker execution")
    expires_at: float = Field(default_factory=lambda: time.time() + 300.0, description="Epoch expiration timestamp")
    required_policies: list[str] = Field(
        default_factory=lambda: ["sandbox_isolation", "network_whitelist", "credential_validity"],
        description="List of security policies that must remain valid at pre-start",
    )


class DispatchReceiptDTO(BaseModel):
    """Receipt acknowledged upon successful transaction initialization."""

    dispatch_id: str = Field(..., description="Transaction dispatch ID")
    acknowledged_seq: int = Field(..., description="Acknowledged journal sequence number")
    prestart_verified: bool = Field(..., description="Whether pre-start policy was confirmed")
    peer_status: str = Field(default="accepted", description="Status code (accepted / active / complete)")


class PrestartRevalidateRequest(BaseModel):
    """Payload to revalidate security policies immediately before remote execution."""

    active_policies: dict[str, bool] = Field(..., description="Currently active security policies map")


class PrestartRevalidateResponse(BaseModel):
    """Outcome of pre-start fail-closed policy verification."""

    dispatch_id: str = Field(..., description="Target dispatch transaction ID")
    passed: bool = Field(..., description="Whether all required policies passed revalidation")
    checked_policies_count: int = Field(..., description="Number of required policies verified")


class EvidenceSubmitRequest(BaseModel):
    """Payload to submit structured evidence from remote worker."""

    evidence_type: str = Field(..., description="Artifact, execution log, or tool output")
    size_bytes: int = Field(..., ge=0, description="Payload size in bytes")
    content_digest: str = Field(..., description="Content hash of evidence")
    description: str = Field(default="", description="Summary description")


class EvidenceSubmitResponse(BaseModel):
    """Verdict on evidence bounded admission."""

    evidence_id: str = Field(..., description="Unique evidence identifier")
    dispatch_id: str = Field(..., description="Target dispatch transaction ID")
    admitted: bool = Field(..., description="Whether evidence conformed to bounds and was admitted")
    size_bytes: int = Field(..., description="Size in bytes")


class JournalEntryDTO(BaseModel):
    """Representation of an append-only journal event."""

    journal_id: str = Field(..., description="Unique journal record ID")
    dispatch_id: str = Field(..., description="Associated dispatch transaction ID")
    seq: int = Field(..., description="Monotonically increasing sequence number")
    entry_type: str = Field(..., description="State transition or evidence event type")
    timestamp: float = Field(..., description="Epoch timestamp of recording")
    payload_hash: str = Field(..., description="SHA-256 digest of payload")
    metadata: dict[str, str] = Field(default_factory=dict, description="Diagnostic key-value context")


class RecoveryPlanDTO(BaseModel):
    """Idempotent resume directive computed after a node restart or network drop."""

    dispatch_id: str = Field(..., description="Target dispatch transaction")
    last_known_seq: int = Field(..., description="Last verified journal sequence recorded")
    last_entry_type: str = Field(..., description="Last committed journal phase")
    can_resume: bool = Field(..., description="Whether task state is safe for idempotent continuation")
    resume_action: str = Field(..., description="Action to take: idempotent_continue_execution / fail_closed")
