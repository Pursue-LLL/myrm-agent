"""
[POS] app/schemas/media_artifact_grants.py
[INPUT] pydantic
[OUTPUT] MediaArtifactGrant schemas, request/response DTOs, metrics DTO
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluateGrantRequestDTO(BaseModel):
    """Payload to evaluate role-scoped inline rendering eligibility for an artifact."""

    session_id: str = Field(..., description="Unique conversational session ID")
    artifact_id: str = Field(..., description="Unique media/artifact identifier")
    producer_role: str = Field(
        ...,
        description="Originator role: ASSISTANT, TOOL, USER, EXTERNAL_UNTRUSTED",
    )
    mime_type: str = Field(..., description="MIME content type of artifact")
    checksum_sha256: str = Field(
        default="",
        description="Optional SHA256 digest of media payload for integrity verification",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary diagnostic tags associated with artifact",
    )


class RevokeGrantRequestDTO(BaseModel):
    """Payload to revoke an existing inline render grant."""

    session_id: str = Field(..., description="Session ID owning the artifact")
    artifact_id: str = Field(..., description="Artifact ID to revoke")
    reason: str = Field(default="Explicit revocation", description="Audit reason for revocation")


class MediaArtifactGrantResponseDTO(BaseModel):
    """Grant record representation for session artifact."""

    artifact_id: str = Field(..., description="Artifact identifier")
    session_id: str = Field(..., description="Session identifier")
    producer_role: str = Field(..., description="Verified origin role")
    mime_type: str = Field(..., description="Content type")
    is_inline_allowed: bool = Field(..., description="Whether inline presentation is authorized")
    grant_status: str = Field(..., description="Grant status string")
    granted_at_epoch: float = Field(..., description="Epoch timestamp of grant")
    checksum_sha256: str = Field(..., description="Payload digest")
    metadata: dict[str, str] = Field(default_factory=dict, description="Diagnostic tags")


class GrantEvaluationResponseDTO(BaseModel):
    """Decision outcome from evaluating artifact inline render request."""

    is_allowed: bool = Field(..., description="Inline render permission decision")
    grant_status: str = Field(..., description="Status classification")
    rendered_preview_mode: str = Field(..., description="Rendering strategy: INLINE, DOWNLOAD_LINK, etc.")
    diagnostic_reason: str = Field(..., description="Human-readable decision explanation")
    artifact_id: str = Field(..., description="Evaluated artifact ID")
    session_id: str = Field(..., description="Session context ID")


class RevokeGrantResponseDTO(BaseModel):
    """Result of revoking an artifact inline display grant."""

    session_id: str = Field(..., description="Session identifier")
    artifact_id: str = Field(..., description="Artifact identifier")
    revoked: bool = Field(..., description="Whether revocation succeeded")
    reason: str = Field(..., description="Audit reason recorded")


class MediaArtifactGrantMetricsDTO(BaseModel):
    """Operational metrics snapshot for media artifact role-scoped grants."""

    grants_evaluated_total: int = Field(..., description="Total evaluation calls")
    inline_granted_total: int = Field(..., description="Total inline presentations authorized")
    external_blocked_total: int = Field(..., description="Total untrusted origins blocked/demoted")
    grants_revoked_total: int = Field(..., description="Total active grants revoked")
