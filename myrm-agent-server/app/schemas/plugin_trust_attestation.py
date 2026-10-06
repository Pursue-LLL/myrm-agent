"""Pydantic schemas for Plugin Trust Chain and Dynamic Capability Attestation.

[POS] app/schemas/plugin_trust_attestation.py
[INPUT] pydantic
[OUTPUT] SignPluginPackageRequest, SignedPluginPackageResponse, VerifyPluginPackageRequest, VerifyPluginPackageResponse, IssueAttestationTokenRequest, AttestationTokenResponse, ValidateOperationRequest, ValidateOperationResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SignPluginPackageRequest(BaseModel):
    """Request payload to cryptographically sign a vetted plugin package."""

    model_config = ConfigDict(frozen=True)

    plugin_id: str = Field(..., description="Unique plugin identifier (e.g. org.myrm.fetcher)")
    version: str = Field(..., description="Semantic version string")
    payload_sha256: str = Field(..., description="SHA-256 hash of plugin code and manifest payload")
    trust_tier: str = Field(
        default="OFFICIAL_VERIFIED",
        description="Assigned trust tier: OFFICIAL_VERIFIED, VETTED_COMMUNITY, UNREVIEWED_COMMUNITY",
    )
    signer_identity: str = Field(
        default="myrm-official-ca",
        description="Signer identity or certification authority",
    )


class SignedPluginPackageResponse(BaseModel):
    """Response containing digital signature package for a plugin release."""

    model_config = ConfigDict(frozen=True)

    plugin_id: str
    version: str
    payload_sha256: str
    signature: str
    signer_identity: str
    trust_tier: str
    signed_at: float


class VerifyPluginPackageRequest(BaseModel):
    """Request payload to verify the integrity and signature of a plugin release."""

    model_config = ConfigDict(frozen=True)

    package: SignedPluginPackageResponse
    actual_payload_sha256: str = Field(
        ...,
        description="SHA-256 computed on the deployed plugin payload",
    )


class VerifyPluginPackageResponse(BaseModel):
    """Result of plugin package verification."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    trust_tier: str
    error_message: str | None = None


class IssueAttestationTokenRequest(BaseModel):
    """Request payload to issue a runtime capability attestation token."""

    model_config = ConfigDict(frozen=True)

    plugin_id: str
    version: str
    network_domains: list[str] = Field(default_factory=list)
    file_access_scope: str = Field(default="WORKSPACE_ONLY")
    allow_shell_exec: bool = Field(default=False)
    validity_seconds: int = Field(default=3600, ge=60, le=86400)


class AttestationTokenResponse(BaseModel):
    """Dynamic capability proof token issued to sandboxed plugin."""

    model_config = ConfigDict(frozen=True)

    token_id: str
    plugin_id: str
    granted_domains: list[str]
    granted_file_scope: str
    allow_shell: bool
    issued_at: float
    expires_at: float
    token_hmac: str


class ValidateOperationRequest(BaseModel):
    """Request payload to validate a runtime operation against an attestation token."""

    model_config = ConfigDict(frozen=True)

    token: AttestationTokenResponse
    target_domain: str | None = Field(default=None)
    requires_shell: bool = Field(default=False)


class ValidateOperationResponse(BaseModel):
    """Result of runtime capability validation."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str
