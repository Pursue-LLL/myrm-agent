"""
[POS] app/schemas/readonly_research_sandbox.py
[INPUT] pydantic, enum
[OUTPUT] ResearchModeEnum, LeaseStatusEnum, GrantLeaseRequest, ReadOnlyLeaseResponse, RevokeLeaseResponse, ToolEvaluationRequest, ToolEvaluationResponse, TakeSnapshotRequest, WorkspaceSnapshotResponse, WriteEphemeralFileRequest, EphemeralFileResponse, PurgeOverlayResponse, VerifyPurityRequest, VerifyPurityResponse, ShieldBadgeResponse, ReadOnlyResearchMetricsResponse

Pydantic schemas for Read-Only Autonomous Research Lease & Immutable Snapshot Sandbox Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ResearchModeEnum(StrEnum):
    """Autonomous research operational mode."""

    GENERAL_INTERACTIVE = "GENERAL_INTERACTIVE"
    AUTONOMOUS_RESEARCH = "AUTONOMOUS_RESEARCH"
    BACKGROUND_STUDY = "BACKGROUND_STUDY"


class LeaseStatusEnum(StrEnum):
    """Lifecycle status of a read-only research lease."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class GrantLeaseRequest(BaseModel):
    """Payload to grant dynamic read-only research lease to session."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    research_mode: ResearchModeEnum = Field(
        default=ResearchModeEnum.AUTONOMOUS_RESEARCH, description="Research mode"
    )
    ttl_seconds: float | None = Field(
        default=3600.0, ge=1.0, description="Lease time-to-live in seconds"
    )
    custom_allowed_tools: list[str] | None = Field(
        default=None, description="Optional safe read-only tools override"
    )


class ReadOnlyLeaseResponse(BaseModel):
    """Descriptor of granted or active read-only lease."""

    lease_id: str = Field(..., description="Unique lease identifier")
    session_id: str = Field(..., description="Session identifier")
    research_mode: ResearchModeEnum = Field(..., description="Research mode")
    granted_at: float = Field(..., description="Epoch granted at")
    expires_at: float = Field(..., description="Epoch expires at")
    status: LeaseStatusEnum = Field(..., description="Current lease status")
    allowed_tools: list[str] = Field(..., description="Whitelisted read-only tools")
    blocked_side_effects: list[str] = Field(..., description="Physically stripped tools")


class RevokeLeaseResponse(BaseModel):
    """Outcome of lease revocation."""

    session_id: str = Field(..., description="Session identifier")
    status: LeaseStatusEnum = Field(..., description="Status after revocation")
    message: str = Field(..., description="Explanation message")


class ToolEvaluationRequest(BaseModel):
    """Payload to check whether tool invocation is permissible under active lease."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    tool_name: str = Field(..., min_length=1, description="Tool function name")


class ToolEvaluationResponse(BaseModel):
    """Outcome of tool boundary check."""

    is_allowed: bool = Field(..., description="True if allowed to run")
    explanation: str = Field(..., description="Justification")
    session_id: str = Field(..., description="Session identifier")
    is_read_only_enforced: bool = Field(..., description="True if read-only lease is active")


class TakeSnapshotRequest(BaseModel):
    """Payload to capture baseline snapshot of protected workspace."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    baseline_files: dict[str, str] = Field(..., description="Map of relative paths to text content")


class WorkspaceSnapshotResponse(BaseModel):
    """Descriptor of captured immutable baseline snapshot."""

    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    session_id: str = Field(..., description="Session identifier")
    baseline_timestamp: float = Field(..., description="Timestamp of baseline capture")
    root_digest: str = Field(..., min_length=64, max_length=64, description="SHA-256 root digest")
    tracked_files_count: int = Field(..., ge=0, description="Number of baseline files tracked")


class WriteEphemeralFileRequest(BaseModel):
    """Payload to write transient research output into memory CoW layer."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    virtual_path: str = Field(..., min_length=1, description="Virtual relative path")
    content: str = Field(..., description="File text content")


class EphemeralFileResponse(BaseModel):
    """Descriptor of file staged in in-memory CoW layer."""

    virtual_path: str = Field(..., description="Virtual relative path")
    sha256_hash: str = Field(..., description="SHA-256 content hash")
    written_at: float = Field(..., description="Epoch written at")
    size_bytes: int = Field(..., ge=0, description="Size in bytes")


class PurgeOverlayResponse(BaseModel):
    """Outcome of purging in-memory CoW layer."""

    session_id: str = Field(..., description="Session identifier")
    purged_files_count: int = Field(..., ge=0, description="Number of transient files destroyed")
    message: str = Field(..., description="Confirmation message")


class VerifyPurityRequest(BaseModel):
    """Payload to verify current workspace files against baseline snapshot."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    current_files: dict[str, str] = Field(..., description="Map of relative paths to text content")


class VerifyPurityResponse(BaseModel):
    """Verification verdict of workspace purity."""

    session_id: str = Field(..., description="Session identifier")
    is_pure: bool = Field(..., description="True if workspace is 100% bit-identical to baseline")
    explanation: str = Field(..., description="Detailed verification explanation")


class ShieldBadgeResponse(BaseModel):
    """Real-time UI security indicator badge."""

    is_read_only_active: bool = Field(..., description="True if read-only lease active")
    active_lease_id: str | None = Field(default=None, description="Active lease ID if present")
    research_mode: ResearchModeEnum = Field(..., description="Active research mode")
    cow_overlay_active: bool = Field(..., description="True if CoW layer holds staged files")
    workspace_purity_verified: bool = Field(..., description="True if baseline purity verified")
    badge_label: str = Field(..., description="Display label string")


class ReadOnlyResearchMetricsResponse(BaseModel):
    """Cumulative operational metrics for read-only research sandbox subsystem."""

    total_leases_granted: int = Field(..., ge=0)
    active_leases_count: int = Field(..., ge=0)
    leases_revoked_count: int = Field(..., ge=0)
    write_attempts_blocked: int = Field(..., ge=0)
    ephemeral_cow_files_staged: int = Field(..., ge=0)
    overlays_purged_count: int = Field(..., ge=0)
    purity_verifications_count: int = Field(..., ge=0)
