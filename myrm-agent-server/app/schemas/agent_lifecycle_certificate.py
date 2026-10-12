"""
[POS] app/schemas/agent_lifecycle_certificate.py
[INPUT] pydantic
[OUTPUT] CertificateStatusEnum, RevocationReasonEnum, CertificateHealthStatusEnum, MintAgentCertificateRequest, AgentCertificateResponse, PreflightVerificationRequest, PreflightVerificationResponse, EmergencyRevocationRequest, RevocationRecordResponse, CrlSnapshotResponse, CertificateHealthSummaryResponse, CertificateHealthDashboardResponse

Pydantic schemas for Agent Lifecycle Digital Certificate and Emergency Revocation Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CertificateStatusEnum(StrEnum):
    """Lifecycle status of an agent digital certificate."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"


class RevocationReasonEnum(StrEnum):
    """RFC 5280 compliant revocation reasons."""

    KEY_COMPROMISE = "KEY_COMPROMISE"
    CA_COMPROMISE = "CA_COMPROMISE"
    AFFILIATION_CHANGED = "AFFILIATION_CHANGED"
    SUPERSEDED = "SUPERSEDED"
    CESSATION_OF_OPERATION = "CESSATION_OF_OPERATION"
    MALICIOUS_BACKDOOR_DETECTED = "MALICIOUS_BACKDOOR_DETECTED"
    ADMIN_EMERGENCY_SHUTDOWN = "ADMIN_EMERGENCY_SHUTDOWN"


class CertificateHealthStatusEnum(StrEnum):
    """Health classification for agent certificates."""

    HEALTHY = "HEALTHY"
    EXPIRING_SOON = "EXPIRING_SOON"
    CRITICAL_EXPIRY = "CRITICAL_EXPIRY"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class MintAgentCertificateRequest(BaseModel):
    """Request to mint and sign an agent digital certificate."""

    agent_id: str = Field(..., min_length=1, max_length=128, description="Target agent unique identifier.")
    subject_dn: str = Field(..., min_length=1, max_length=256, description="Distinguished Name of the agent subject.")
    validity_days: int = Field(default=365, ge=1, le=3650, description="Certificate validity duration in days.")
    attributes: dict[str, str] = Field(default_factory=dict, description="Metadata tags and clearance attributes.")


class AgentCertificateResponse(BaseModel):
    """Full cryptographic digital certificate model."""

    cert_id: str = Field(..., description="Unique certificate identifier.")
    agent_id: str = Field(..., description="Bound agent ID.")
    issuer_dn: str = Field(..., description="Issuer CA Distinguished Name.")
    subject_dn: str = Field(..., description="Subject Distinguished Name.")
    serial_number: str = Field(..., description="Serial number issued by CA.")
    fingerprint_sha256: str = Field(..., description="SHA-256 certificate fingerprint.")
    not_before: float = Field(..., description="Valid start epoch timestamp.")
    not_after: float = Field(..., description="Valid expiration epoch timestamp.")
    status: CertificateStatusEnum = Field(..., description="Current certificate status.")
    signature_hex: str = Field(..., description="Cryptographic CA signature in hex.")
    public_key_pem: str = Field(..., description="Public key in PEM format.")
    attributes: dict[str, str] = Field(default_factory=dict, description="Custom metadata attributes.")


class PreflightVerificationRequest(BaseModel):
    """Request to verify an agent certificate prior to sandbox execution."""

    cert_id: str = Field(..., min_length=1, description="Certificate ID to verify.")
    simulated_current_time: float | None = Field(default=None, description="Optional override time for testing.")


class PreflightVerificationResponse(BaseModel):
    """Verification verdict on agent certificate."""

    is_allowed: bool = Field(..., description="True if agent is permitted to execute.")
    status: CertificateStatusEnum = Field(..., description="Resulting certificate status.")
    message: str = Field(..., description="Human-readable decision explanation.")
    signature_valid: bool = Field(..., description="Cryptographic signature verification.")
    not_expired: bool = Field(..., description="Expiration check boolean.")
    not_revoked: bool = Field(..., description="CRL revocation check boolean.")
    issuer_trusted: bool = Field(..., description="Trust root issuer check boolean.")


class EmergencyRevocationRequest(BaseModel):
    """Request to immediately revoke an agent certificate and broadcast to CRL."""

    cert_id: str = Field(..., min_length=1, description="Target certificate ID to revoke.")
    reason: RevocationReasonEnum = Field(
        default=RevocationReasonEnum.MALICIOUS_BACKDOOR_DETECTED,
        description="Reason for emergency revocation.",
    )
    revoked_by: str = Field(default="security-admin", description="Admin identifier triggering revocation.")


class RevocationRecordResponse(BaseModel):
    """Single certificate revocation record in CRL."""

    serial_number: str = Field(..., description="Serial number revoked.")
    cert_id: str = Field(..., description="Certificate ID.")
    agent_id: str = Field(..., description="Agent ID.")
    revocation_timestamp: float = Field(..., description="Revocation epoch timestamp.")
    reason: RevocationReasonEnum = Field(..., description="Revocation reason.")
    revoked_by: str = Field(..., description="Admin who revoked.")


class CrlSnapshotResponse(BaseModel):
    """Active Certificate Revocation List (CRL) snapshot."""

    total_revoked: int = Field(..., ge=0, description="Total active revoked certificates.")
    records: list[RevocationRecordResponse] = Field(..., description="List of revocation records.")


class CertificateHealthSummaryResponse(BaseModel):
    """Health diagnostic summary for an individual certificate."""

    cert_id: str = Field(..., description="Certificate ID.")
    agent_id: str = Field(..., description="Agent ID.")
    health_status: CertificateHealthStatusEnum = Field(..., description="Health status classification.")
    days_until_expiry: float = Field(..., description="Remaining validity in days.")
    is_revoked: bool = Field(..., description="Revocation boolean.")
    requires_renewal: bool = Field(..., description="Renewal urgency flag.")


class CertificateHealthDashboardResponse(BaseModel):
    """Aggregated health dashboard across all minted certificates."""

    total_certificates: int = Field(..., ge=0, description="Total certificates managed.")
    healthy_count: int = Field(..., ge=0, description="Count of certificates in HEALTHY state.")
    expiring_soon_count: int = Field(..., ge=0, description="Expiring within 30 days.")
    critical_expiry_count: int = Field(..., ge=0, description="Expiring within 7 days.")
    expired_count: int = Field(..., ge=0, description="Expired count.")
    revoked_count: int = Field(..., ge=0, description="Revoked count.")
    summaries: list[CertificateHealthSummaryResponse] = Field(..., description="Individual certificate health summaries.")
