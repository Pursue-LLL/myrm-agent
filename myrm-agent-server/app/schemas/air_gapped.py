"""Pydantic schemas for Air-Gapped Sovereign Intelligence and Zero-Egress Compliance.

[INPUT]
None.

[OUTPUT]
DTO models for egress mode governance, zero-egress cryptographic assertions, and sovereign compliance dossiers.

[POS]
Server schemas. Exposes typed contracts for enterprise air-gapped compliance and zero-egress auditing.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class EgressAttemptDto(BaseModel):
    """Telemetry inspection record of a network egress attempt."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(..., description="Unique attempt identifier")
    destination_host: str = Field(..., description="Target hostname or IP address")
    destination_port: int = Field(..., description="Target port number")
    protocol: str = Field(..., description="Network protocol (tcp, udp, http, https)")
    allowed: bool = Field(..., description="Whether connection was permitted")
    reason: str = Field(..., description="Security policy decision explanation")
    tier: str = Field(..., description="Operational egress tier at the time of attempt")
    timestamp: float = Field(..., description="Unix timestamp of attempt")


class SetEgressTierRequest(BaseModel):
    """Payload to configure the active operational egress tier."""

    model_config = ConfigDict(extra="forbid")

    tier: str = Field(..., description="Egress tier: 'standard', 'conservative', or 'air_gapped_sovereign'")


class EgressTierStatusResponse(BaseModel):
    """Active network egress policy tier and runtime telemetry."""

    model_config = ConfigDict(extra="forbid")

    current_tier: str = Field(..., description="Current active egress tier")
    is_air_gapped: bool = Field(..., description="True if sovereign air-gapped mode is engaged")
    total_attempts: int = Field(..., description="Total outbound network connection checks")
    blocked_attempts: int = Field(..., description="Count of blocked external connections")
    active_allowlist_count: int = Field(..., description="Count of permitted domains in allowlist")


class ZeroEgressAssertionResponse(BaseModel):
    """Formal audit proof verifying 0 external connections occurred."""

    model_config = ConfigDict(extra="forbid")

    total_attempts: int = Field(..., description="Total connections evaluated")
    blocked_attempts: int = Field(..., description="Count of blocked external connection attempts")
    external_egress_count: int = Field(..., description="Count of external non-loopback connections (must be 0)")
    is_zero_egress_compliant: bool = Field(..., description="True if 0 external egress occurred")
    assertion_hash: str = Field(..., description="SHA-256 cryptographic proof hash over attempt history")
    verified_at: float = Field(..., description="Unix verification timestamp")


class SovereignComplianceDossierResponse(BaseModel):
    """Exportable enterprise air-gapped sovereign compliance whitepaper dossier."""

    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(..., description="Enterprise or tenant identifier")
    compliance_standard: str = Field(..., description="Target regulatory standard")
    tier: str = Field(..., description="Current egress control tier")
    zero_egress_assertion: ZeroEgressAssertionResponse = Field(..., description="Assertion proof")
    local_volume_storage_path: str = Field(..., description="Physical sandbox storage mount path")
    encryption_at_rest_enabled: bool = Field(..., description="Whether storage at rest is encrypted")
    data_sovereignty_declaration: str = Field(..., description="Legal and technical data non-egress declaration")
    sha256_dossier_signature: str = Field(..., description="Digital signature of compliance dossier")
    generated_at: float = Field(default_factory=time.time, description="Generation timestamp")
