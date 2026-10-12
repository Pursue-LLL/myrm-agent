"""Pydantic DTO schemas for Enterprise Zero-Egress Audit Ledger & Asset Provenance.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for tamper-evident audit records, zero-egress attestation certificates,
  and IP asset provenance dossiers.

[POS]
- Server schemas. Exposes typed contracts for enterprise zero-egress auditing and IP indemnification.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RecordAuditEventRequest(BaseModel):
    """Request payload to log a cross-system event into the tamper-evident audit ledger."""

    model_config = ConfigDict(extra="forbid")

    actor: str = Field(..., description="Agent role, user ID, or system component initiating the action")
    action_type: str = Field(..., description="Action category (e.g. DATABASE_QUERY, FILE_WRITE, MODEL_INVOKE)")
    resource_target: str = Field(..., description="Target database, table, file, or remote endpoint")
    input_payload: str = Field(default="", description="Input parameters or query payload string")
    output_payload: str = Field(default="", description="Output result or response summary payload string")
    boundary_state: str = Field(
        default="SANDBOX_CONFINED",
        description="Confinement state: SANDBOX_CONFINED, APPROVED_EGRESS_TUNNEL, or DISALLOWED_VIOLATION",
    )


class AuditLedgerRecordDto(BaseModel):
    """Chained audit record DTO."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(..., description="Unique record identifier")
    sequence_number: int = Field(..., description="Monotonically increasing sequence index")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp")
    actor: str = Field(..., description="Executing actor")
    action_type: str = Field(..., description="Action classification")
    resource_target: str = Field(..., description="Target resource")
    input_sha256: str = Field(..., description="SHA-256 hash of input data")
    output_sha256: str = Field(..., description="SHA-256 hash of output data")
    boundary_state: str = Field(..., description="Network boundary confinement state")
    previous_record_hash: str = Field(..., description="Hash of the preceding ledger record")
    current_record_hash: str = Field(..., description="Cryptographic hash of the current record")
    compliance_standard: str = Field(default="HIPAA_SOC2_COMPLIANT", description="Compliance standard tag")


class VerifyLedgerIntegrityResponse(BaseModel):
    """Outcome of ledger hash chain verification."""

    model_config = ConfigDict(extra="forbid")

    is_intact: bool = Field(..., description="True if no record has been tampered with or removed")
    total_records: int = Field(..., description="Count of chained records validated")
    audit_notes: str = Field(default="", description="Audit report notes")


class GenerateZeroEgressCertificateRequest(BaseModel):
    """Request payload to issue a zero-egress compliance attestation certificate."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Active session identifier")
    tenant_id: str = Field(..., description="Enterprise tenant identifier")
    sandbox_id: str = Field(..., description="Isolated execution sandbox identifier")
    attestation_level: str = Field(
        default="ENTERPRISE_ZERO_EGRESS",
        description="STANDARD, ENTERPRISE_ZERO_EGRESS, or HIPAA_SOC2_CERTIFIED",
    )


class ZeroEgressAttestationCertificateDto(BaseModel):
    """Cryptographically signed compliance attestation certificate."""

    model_config = ConfigDict(extra="forbid")

    certificate_id: str = Field(..., description="Certificate unique identifier")
    session_id: str = Field(..., description="Session identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    sandbox_id: str = Field(..., description="Sandbox identifier")
    attestation_level: str = Field(..., description="Compliance attestation tier")
    zero_data_retention_guaranteed: bool = Field(..., description="Guarantee that no data is retained")
    no_model_training_guaranteed: bool = Field(..., description="Guarantee that data is never used for training")
    environment_digest_sha256: str = Field(..., description="Cryptographic digest of environment parameters")
    signature: str = Field(..., description="HMAC digital signature of the certificate")
    issued_at_iso: str = Field(..., description="Issuance timestamp")
    issuer: str = Field(default="Myrm-Enterprise-Security-Authority", description="Issuing authority")


class CreateAssetProvenanceRequest(BaseModel):
    """Request payload to create an IP provenance dossier for generated code or media."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., description="Unique generated asset identifier")
    asset_name: str = Field(..., description="Filename or label")
    media_type: str = Field(..., description="MIME media type (e.g. text/x-python, text/markdown)")
    content: str = Field(..., description="Generated asset text or base64 content")
    session_id: str = Field(..., description="Generating session ID")
    prompt_text: str = Field(..., description="Original user prompt from which asset was generated")
    foundation_model_id: str = Field(..., description="Model identifier (e.g. claude-3-7-sonnet)")
    license_type: str = Field(default="PROPRIETARY_WORK_FOR_HIRE", description="Assigned license terms")
    ip_tier: str = Field(
        default="ENTERPRISE_INDEMNIFIED",
        description="ENTERPRISE_INDEMNIFIED, PROVENANCE_VERIFIED, or UNVERIFIED_COMMUNITY",
    )


class AssetProvenanceDossierDto(BaseModel):
    """Intellectual property provenance record DTO."""

    model_config = ConfigDict(extra="forbid")

    dossier_id: str = Field(..., description="Dossier identifier")
    asset_id: str = Field(..., description="Asset identifier")
    asset_name: str = Field(..., description="Asset name")
    media_type: str = Field(..., description="Media type")
    content_sha256: str = Field(..., description="Content hash")
    session_id: str = Field(..., description="Generating session ID")
    origin_prompt_sha256: str = Field(..., description="Prompt hash")
    foundation_model_id: str = Field(..., description="Model used")
    ip_tier: str = Field(..., description="IP cleanliness tier")
    license_type: str = Field(..., description="License type")
    digital_signature: str = Field(..., description="Cryptographic signature")
    created_at_iso: str = Field(..., description="Creation timestamp")


class VerifyAssetProvenanceRequest(BaseModel):
    """Request payload to verify asset content against registered provenance dossier."""

    model_config = ConfigDict(extra="forbid")

    dossier: AssetProvenanceDossierDto = Field(..., description="Registered provenance dossier")
    content: str = Field(..., description="Asset content to verify against registered hash")


class VerifyAssetProvenanceResponse(BaseModel):
    """Provenance verification outcome."""

    model_config = ConfigDict(extra="forbid")

    is_verified: bool = Field(..., description="True if content digest exactly matches dossier")
    asset_id: str = Field(..., description="Asset identifier")
    audit_notes: str = Field(default="", description="Verification notes")
