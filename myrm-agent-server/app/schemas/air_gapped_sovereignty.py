"""
[POS] app/schemas/air_gapped_sovereignty.py
[INPUT] pydantic, enum
[OUTPUT] NetworkConnectivityModeEnum, ModelFallbackTargetSchema, OfflineTrustAnchorSchema, OfflineCertValidationRequest, OfflineCertValidationResponse, ImportCrlRequest, ImportCrlResponse, ModelResolutionRequest, ModelResolutionResponse, AuditBundlePackRequest, AuditBundleResponse, AuditBundleVerifyRequest, AuditBundleVerifyResponse, ModeUpdateRequest, ModeResponse, SovereignCryptoHashRequest, SovereignCryptoHashResponse, AirGappedSovereigntyMetricsResponse

Pydantic schemas for Air-Gapped Offline Trust Store and Sovereign Model Fallback Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NetworkConnectivityModeEnum(StrEnum):
    """Network operational environment mode."""

    ONLINE = "ONLINE"
    AIR_GAPPED_ISOLATED = "AIR_GAPPED_ISOLATED"
    DEGRADED_FAILOVER = "DEGRADED_FAILOVER"


class ModelFallbackTargetSchema(BaseModel):
    """Target execution spec for local sovereign or remote models."""

    model_id: str = Field(..., min_length=1, max_length=128, description="Target model identifier")
    endpoint_url: str = Field(..., min_length=1, description="Model inference endpoint URL")
    provider: str = Field(default="ollama", description="Model runtime provider (e.g., ollama, vllm)")
    is_local_sovereign: bool = Field(default=True, description="True if weights execute locally without egress")
    context_window: int = Field(default=32768, ge=1024, description="Context token window limit")


class OfflineTrustAnchorSchema(BaseModel):
    """Offline Root CA trust anchor."""

    ca_name: str = Field(..., min_length=1, max_length=128, description="Accredited Root CA name")
    root_cert_pem: str = Field(..., min_length=1, description="Root CA certificate in PEM format")
    valid_until: float = Field(..., ge=0.0, description="Expiration epoch timestamp")
    fingerprint_sm3: str = Field(..., min_length=64, max_length=64, description="SM3 digest of root certificate")


class OfflineCertValidationRequest(BaseModel):
    """Request payload to validate certificate against offline anchors and CRL."""

    cert_pem: str = Field(..., min_length=1, description="Client or server certificate PEM")
    cert_serial: str = Field(..., min_length=1, description="Certificate serial number")
    issuer_ca: str = Field(..., min_length=1, description="Claimed issuer root CA name")
    valid_until: float = Field(..., ge=0.0, description="Certificate expiry timestamp")


class OfflineCertValidationResponse(BaseModel):
    """Offline certificate verification result."""

    is_valid: bool = Field(..., description="True if valid and trusted")
    reason: str = Field(..., description="Validation outcome explanation")
    ca_name: str | None = Field(default=None, description="Matched CA anchor name")
    is_revoked: bool = Field(default=False, description="True if found in offline CRL")
    fingerprint_sm3: str | None = Field(default=None, description="Calculated SM3 fingerprint")


class ImportCrlRequest(BaseModel):
    """Payload to import revoked serials into offline CRL."""

    revoked_serials: list[str] = Field(..., min_length=1, description="List of revoked certificate serial numbers")


class ImportCrlResponse(BaseModel):
    """Offline CRL import result."""

    imported_count: int = Field(..., ge=0, description="Newly revoked certificate count")
    total_revoked_count: int = Field(..., ge=0, description="Total active revoked certificates")


class ModelResolutionRequest(BaseModel):
    """Request to resolve execution target under network constraints."""

    requested_model_id: str = Field(..., min_length=1, description="Preferred model identifier")
    is_remote_healthy: bool = Field(default=True, description="Whether remote gateway is reachable")


class ModelResolutionResponse(BaseModel):
    """Resulting model target resolution."""

    effective_target: ModelFallbackTargetSchema = Field(..., description="Effective execution model target")
    was_fallback: bool = Field(..., description="True if fallback diversion occurred")
    reason: str = Field(..., description="Routing explanation")
    active_mode: NetworkConnectivityModeEnum = Field(..., description="Current network mode")


class AuditBundlePackRequest(BaseModel):
    """Request to pack evidentiary audit records."""

    records: list[dict[str, str]] = Field(..., min_length=1, description="Audit record payloads")
    bundle_id: str | None = Field(default=None, description="Optional bundle identifier")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata tags")


class AuditBundleResponse(BaseModel):
    """Sealed air-gapped evidentiary audit bundle record."""

    bundle_id: str = Field(..., description="Unique bundle identifier")
    timestamp: float = Field(..., description="Sealing timestamp")
    record_count: int = Field(..., ge=0, description="Total encapsulated records")
    sm3_root_digest: str = Field(..., min_length=64, max_length=64, description="SM3 Merkle/chain digest")
    is_sealed: bool = Field(default=True, description="Tamper-evident seal flag")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class AuditBundleVerifyRequest(BaseModel):
    """Request to verify integrity of an evidentiary bundle against raw records."""

    bundle: AuditBundleResponse = Field(..., description="Sealed bundle descriptor")
    raw_records: list[dict[str, str]] = Field(..., description="Raw records to cross-check")


class AuditBundleVerifyResponse(BaseModel):
    """Integrity verification verdict."""

    is_valid: bool = Field(..., description="True if records match sealed SM3 root digest")
    reason: str = Field(..., description="Detailed verification explanation")


class ModeUpdateRequest(BaseModel):
    """Payload to update network connectivity mode."""

    mode: NetworkConnectivityModeEnum = Field(..., description="Desired network mode")


class ModeResponse(BaseModel):
    """Active network mode response."""

    active_mode: NetworkConnectivityModeEnum = Field(..., description="Current network mode")


class SovereignCryptoHashRequest(BaseModel):
    """Payload to compute SM3 hash."""

    data: str = Field(..., description="Data string to hash")


class SovereignCryptoHashResponse(BaseModel):
    """SM3 hash computation response."""

    algorithm: str = Field(default="SM3 (GM/T 0004-2012)", description="Algorithm name")
    sm3_digest: str = Field(..., min_length=64, max_length=64, description="Hexadecimal SM3 digest")


class AirGappedSovereigntyMetricsResponse(BaseModel):
    """Cumulative operational metrics for air-gapped sovereignty subsystem."""

    total_offline_validations: int = Field(..., ge=0)
    valid_certificates_count: int = Field(..., ge=0)
    crl_revocation_hits: int = Field(..., ge=0)
    model_fallback_events: int = Field(..., ge=0)
    audit_bundles_sealed: int = Field(..., ge=0)
