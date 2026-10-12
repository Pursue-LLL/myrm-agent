"""
[POS] app/schemas/enterprise_hipaa_compliance.py
[INPUT] pydantic
[OUTPUT] Enterprise BAA / HIPAA compliance conduit & data sovereignty DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BYOCompliantProviderDTO(BaseModel):
    """Bring-Your-Own-Compliant-Provider record DTO."""

    provider_id: str = Field(..., description="Unique provider ID")
    provider_name: str = Field(..., description="Provider display name")
    base_url: str = Field(..., description="Base API endpoint URL")
    tier: str = Field(..., description="Compliance tier: verified_baa_signed, private_vllm_airgap, unverified_public")
    baa_agreement_id: str | None = Field(default=None, description="Executed BAA contract identifier")
    is_zero_training_mandated: bool = Field(default=True, description="Enforces zero-data retention")
    permitted_models: list[str] = Field(..., description="Whitelisted models for this endpoint")


class RegisterProviderRequestDTO(BaseModel):
    """Payload to register a new compliant BYO endpoint."""

    provider_id: str = Field(..., description="Unique provider ID")
    provider_name: str = Field(..., description="Provider display name")
    base_url: str = Field(..., description="Base API endpoint URL")
    tier: str = Field(default="verified_baa_signed", description="verified_baa_signed, private_vllm_airgap, unverified_public")
    baa_agreement_id: str | None = Field(default=None, description="Executed BAA contract identifier")
    is_zero_training_mandated: bool = Field(default=True, description="Enforces zero-data retention")
    permitted_models: list[str] = Field(
        default_factory=lambda: ["gpt-4o", "claude-3-5-sonnet", "deepseek-v3"],
        description="Whitelisted models",
    )


class RecordAuditEventRequestDTO(BaseModel):
    """Payload to append an immutable audit log entry."""

    event_type: str = Field(..., description="Lifecycle action type (e.g. prompt_dispatch, tool_execution)")
    agent_id: str = Field(..., description="Agent or principal identifier")
    session_id: str = Field(..., description="Active session or encounter ID")
    action_summary: str = Field(..., description="Human/auditor readable summary")
    phi_detected: bool = Field(default=False, description="Whether PHI was present in payload")


class HipaaAuditChainEntryDTO(BaseModel):
    """Individual cryptographically hashed ledger entry."""

    entry_id: str = Field(..., description="Unique entry ID")
    sequence_index: int = Field(..., description="Monotonically increasing sequence ID")
    event_type: str = Field(..., description="Lifecycle action type")
    agent_id: str = Field(..., description="Agent or principal ID")
    session_id: str = Field(..., description="Session identifier")
    timestamp: float = Field(..., description="Unix epoch timestamp")
    action_summary: str = Field(..., description="Action summary")
    phi_detected: bool = Field(..., description="PHI flag")
    prev_hash: str = Field(..., description="Previous block cryptographic hash")
    current_hash: str = Field(..., description="Current block cryptographic hash")


class VerifyChainResponseDTO(BaseModel):
    """Integrity audit response for the sequential hash chain."""

    is_valid: bool = Field(..., description="Whether cryptographic chain is unbroken")
    detail: str = Field(..., description="Verification explanation or mismatch location")


class ExportCompliancePackageRequestDTO(BaseModel):
    """Payload to generate verifiable proof package."""

    compliance_standard: str = Field(
        default="hipaa",
        description="Standard identifier: hipaa, baa_enterprise, soc2_type2, gdpr_strict",
    )


class ComplianceExportPackageDTO(BaseModel):
    """Verifiable proof package for enterprise healthcare auditors."""

    export_id: str = Field(..., description="Unique export identifier")
    compliance_standard: str = Field(..., description="Compliance framework identifier")
    generated_at: float = Field(..., description="Export timestamp")
    total_events: int = Field(..., description="Total audited entries count")
    chain_valid: bool = Field(..., description="Chain integrity status")
    summary_digest: str = Field(..., description="Cryptographic root digest of the export")
    ledger_entries: list[HipaaAuditChainEntryDTO] = Field(
        ..., description="Complete audit ledger entries"
    )


class PhiScreeningRequestDTO(BaseModel):
    """Payload to screen text for Protected Health Information."""

    content: str = Field(..., description="Raw text payload to inspect")


class PhiScreeningResponseDTO(BaseModel):
    """Screening outcome for Protected Health Information."""

    is_clean: bool = Field(..., description="Whether content is free of PHI")
    detected_phi_categories: list[str] = Field(..., description="Identified PHI categories")
    sanitized_content: str = Field(..., description="Redacted content safe for dispatch")
    diagnostic: str = Field(..., description="Diagnostic summary")


class ValidateProviderEgressRequestDTO(BaseModel):
    """Payload to validate outbound egress to target provider."""

    provider_id: str = Field(..., description="Target provider ID")
    content: str = Field(..., description="Outbound content to check")


class ValidateProviderEgressResponseDTO(BaseModel):
    """Egress gate routing decision and header injection response."""

    allowed: bool = Field(..., description="Whether egress request is permitted")
    headers: dict[str, str] = Field(..., description="Mandatory headers to inject")
    diagnostic: str = Field(..., description="Diagnostic justification")


class EnterpriseComplianceMetricsDTO(BaseModel):
    """Operational telemetry counters for BAA/HIPAA pipeline."""

    providers_registered_total: int = Field(..., description="Total registered BYO providers")
    audit_events_recorded_total: int = Field(..., description="Total audit events appended")
    phi_violations_blocked_total: int = Field(..., description="Total PHI violation blocks")
    unverified_egress_denied_total: int = Field(..., description="Total unverified egress denials")
    compliance_exports_generated_total: int = Field(..., description="Total compliance packages exported")
    zero_training_headers_injected_total: int = Field(..., description="Total zero-training headers injected")
