"""Pydantic schemas for Physical Sandbox Zero-Leakage Attestation and PII Firewall API.

[POS] app/schemas/sandbox_zero_leakage_pii.py
[INPUT] pydantic
[OUTPUT] IssueAttestationRequest, ZeroLeakageAttestationResponse, VerifyAttestationRequest, VerifyAttestationResponse, ScanPiiRequest, ScanPiiResponse, SignProfileRequest, AgentProfileSignatureResponse, VerifyProfileRequest, VerifyProfileResponse, AuditOperatorRequest, AuditOperatorResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IssueAttestationRequest(BaseModel):
    """Request payload to issue a zero-cross-tenant leakage attestation proof."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(..., description="Unique tenant or user identifier")
    container_id: str = Field(..., description="Dedicated container instance ID")
    dedicated_volume_path: str = Field(..., description="Path to exclusive persistent volume")
    dedicated_database_lock: str = Field(..., description="Unique lock token for private sqlite/qdrant store")
    signer_identity: str = Field(default="myrm-control-plane-ledger", description="Issuing authority identity")


class ZeroLeakageAttestationResponse(BaseModel):
    """Cryptographic zero-leakage attestation proof."""

    model_config = ConfigDict(frozen=True)

    attestation_id: str
    tenant_id: str
    container_id: str
    dedicated_volume_path: str
    dedicated_database_lock: str
    issued_at: float
    signer_identity: str
    attestation_signature: str


class VerifyAttestationRequest(BaseModel):
    """Request payload to verify an attestation proof."""

    model_config = ConfigDict(frozen=True)

    proof: ZeroLeakageAttestationResponse


class VerifyAttestationResponse(BaseModel):
    """Result of attestation proof verification."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    reason: str


class ScanPiiRequest(BaseModel):
    """Request payload to scan and redact high-risk PII and child privacy entities."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., description="Inbound memory content or outbound context text")


class ScanPiiResponse(BaseModel):
    """Sanitized text output and detected privacy violation summary."""

    model_config = ConfigDict(frozen=True)

    original_text: str
    sanitized_text: str
    detected_categories: list[str]
    redaction_count: int
    contains_child_privacy_violation: bool


class AuditOperatorRequest(BaseModel):
    """Request payload to assess 4D operator and model transparency."""

    model_config = ConfigDict(frozen=True)

    operator_name: str
    base_model_id: str
    data_jurisdiction: str = Field(default="local")
    is_codebase_public: bool = Field(default=True)


class AuditOperatorResponse(BaseModel):
    """Four-dimensional operator transparency assessment score and tier."""

    model_config = ConfigDict(frozen=True)

    operator_identity_score: float
    model_transparency_score: float
    data_jurisdiction_score: float
    codebase_auditability_score: float
    overall_score: float
    tier: str
    warnings: list[str]


class SignProfileRequest(BaseModel):
    """Request payload to cryptographically sign an agent profile."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    author: str
    model_id: str
    system_prompt: str
    is_official: bool = True


class AgentProfileSignatureResponse(BaseModel):
    """Signed agent profile package."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    author: str
    model_id: str
    system_prompt_hash: str
    signed_at: float
    signature: str
    is_official_verified: bool


class VerifyProfileRequest(BaseModel):
    """Request payload to verify an agent profile package against system prompt."""

    model_config = ConfigDict(frozen=True)

    profile: AgentProfileSignatureResponse
    actual_system_prompt: str


class VerifyProfileResponse(BaseModel):
    """Verification outcome of an agent profile signature."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    reason: str
