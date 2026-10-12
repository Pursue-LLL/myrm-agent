"""
[POS] app/schemas/governed_write_safety.py
[INPUT] pydantic
[OUTPUT] String-is-never-authority governed write safety DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterOpaqueFileRequestDTO(BaseModel):
    """Payload to register and shield a filesystem path behind an opaque ID."""

    raw_path: str = Field(..., description="Target filesystem path")


class RegisterOpaqueFileResponseDTO(BaseModel):
    """Response containing registered opaque ID."""

    opaque_file_id: str = Field(..., description="Generated secure opaque token (@file_xxxx)")
    raw_path: str = Field(..., description="Original raw path bound in governance layer")


class ProposeEditRequestDTO(BaseModel):
    """Payload to create an atomic governed write proposal."""

    opaque_file_id: str = Field(..., description="Target opaque file token")
    current_disk_content: str = Field(..., description="Base disk content read prior to proposing edit")
    candidate_content: str = Field(..., description="Candidate new content to write")


class GovernedWriteProposalDTO(BaseModel):
    """Proposal metadata bound to base pre-image and candidate content hashes."""

    proposal_id: str = Field(..., description="Unique proposal identifier")
    opaque_file_id: str = Field(..., description="Target opaque file token")
    raw_path: str = Field(..., description="Resolved raw filesystem path")
    base_content_hash: str = Field(..., description="SHA-256 digest of base disk content")
    candidate_content_hash: str = Field(..., description="SHA-256 digest of candidate content")
    candidate_content: str = Field(..., description="Proposed new content")
    status: str = Field(..., description="Proposal state: proposed, approved, stale_rejected, committed")
    lease_token: str | None = Field(default=None, description="Issued single-use write lease token")
    created_at: float = Field(default=0.0, description="Creation epoch timestamp")


class ApproveEditRequestDTO(BaseModel):
    """Payload to approve a proposal and issue single-use write lease."""

    proposal_id: str = Field(..., description="Proposal ID to approve")


class ApproveEditResponseDTO(BaseModel):
    """Approval response carrying single-use lease token."""

    proposal_id: str = Field(..., description="Approved proposal ID")
    lease_token: str = Field(..., description="Single-use write lease token")


class CommitEditRequestDTO(BaseModel):
    """Payload to commit an approved write with base hash re-verification."""

    proposal_id: str = Field(..., description="Proposal ID to commit")
    lease_token: str = Field(..., description="Single-use write lease token")
    current_disk_content: str = Field(..., description="Current disk content at commit time to check staleness")


class PreImageSnapshotDTO(BaseModel):
    """Pre-write snapshot recording prior content before any disk mutation."""

    snapshot_id: str = Field(..., description="Unique snapshot ID")
    opaque_file_id: str = Field(..., description="Target opaque file token")
    raw_path: str = Field(..., description="Raw filesystem path")
    content_sha256: str = Field(..., description="SHA-256 digest of original content")
    timestamp: float = Field(..., description="Creation epoch timestamp")
    content_preview: str = Field(..., description="Preview of original content")


class ConflictRecoveryBundleDTO(BaseModel):
    """Diagnostic and recovery payload generated when concurrent edit conflicts occur."""

    proposal_id: str = Field(..., description="Conflicting proposal ID")
    opaque_file_id: str = Field(..., description="Target opaque file token")
    expected_base_hash: str = Field(..., description="Expected base pre-image hash")
    actual_disk_hash: str = Field(..., description="Actual current disk content hash")
    reason: str = Field(..., description="Explanation of conflict")
    suggested_action: str = Field(
        default="review_concurrent_changes_or_rebase",
        description="Recommended resolution action",
    )


class CommitWriteResultDTO(BaseModel):
    """Outcome of attempting to commit an approved governed write proposal."""

    success: bool = Field(..., description="Whether commit succeeded")
    proposal_id: str = Field(..., description="Proposal identifier")
    status: str = Field(..., description="Final proposal status: committed or stale_rejected")
    pre_image_snapshot_id: str | None = Field(default=None, description="Pre-image snapshot ID if captured")
    verified_disk_hash: str | None = Field(default=None, description="Verified SHA-256 digest of post-write content")
    error_message: str | None = Field(default=None, description="Diagnostic error message if failed")
    conflict_bundle: ConflictRecoveryBundleDTO | None = Field(
        default=None, description="Conflict recovery payload on stale rejection"
    )
