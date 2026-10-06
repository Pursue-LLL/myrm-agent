"""Pydantic schemas for Verifiable Cryptographic Erasure and Complete Data Portability.

[POS] app/schemas/data_erasure_portability.py
[INPUT] pydantic
[OUTPUT] RegisterTenantKeyRequest, TenantKeyResponse, EncryptRecordRequest, EncryptRecordResponse, CryptoEraseRequest, CryptoEraseResponse, PortabilityBundleRequest, PortabilityBundleResponse, VerifyBundleRequest, VerifyBundleResponse, ShredPathRequest, ShredPathResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegisterTenantKeyRequest(BaseModel):
    """Request payload to register a tenant encryption key."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(..., description="Unique tenant or user identifier")


class TenantKeyResponse(BaseModel):
    """Response containing tenant key registration status and fingerprint."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    key_fingerprint: str
    status: str = "ACTIVE"


class ExecuteErasureRequest(BaseModel):
    """Request payload to execute GDPR Article 17 cryptographic erasure and physical shredding."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(..., description="Tenant whose data is being irreversibly destroyed")
    target_resource_types: list[str] = Field(
        default_factory=lambda: ["CONVERSATIONS", "VECTORS", "MEMORY"],
        description="Target resource categories to purge",
    )
    physical_path_to_shred: str | None = Field(
        default=None,
        description="Optional local volume path to multi-pass shred and unlink",
    )
    signer_identity: str = Field(
        default="myrm-trust-ledger",
        description="Certifying authority identity",
    )


class DeletionCertificateResponse(BaseModel):
    """Tamper-evident cryptographic deletion certificate response."""

    model_config = ConfigDict(frozen=True)

    certificate_id: str
    tenant_id: str
    erasure_method: str
    target_resource_types: list[str]
    shredded_bytes: int
    payload_checksum_prior: str
    timestamp: float
    signer_identity: str
    certificate_signature: str


class ErasureResultResponse(BaseModel):
    """Overall outcome of the erasure operation."""

    model_config = ConfigDict(frozen=True)

    success: bool
    tenant_id: str
    erasure_method: str
    certificate: DeletionCertificateResponse | None
    shredded_files_count: int = 0
    shredded_bytes_count: int = 0
    error_message: str | None = None


class VerifyCertificateRequest(BaseModel):
    """Request payload to verify a deletion certificate."""

    model_config = ConfigDict(frozen=True)

    certificate: DeletionCertificateResponse


class VerifyCertificateResponse(BaseModel):
    """Verification outcome of a deletion certificate."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    reason: str


class ExportPortabilityBundleRequest(BaseModel):
    """Request payload to export full tenant digital assets under GDPR Article 20."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    conversations: list[dict[str, str]] = Field(default_factory=list)
    memory_entries: list[dict[str, str]] = Field(default_factory=list)
    agent_configs: list[dict[str, str]] = Field(default_factory=list)


class PortabilityBundleResponse(BaseModel):
    """GDPR Article 20 tamper-evident portable container."""

    model_config = ConfigDict(frozen=True)

    bundle_id: str
    tenant_id: str
    exported_at: float
    conversations: list[dict[str, str]]
    memory_entries: list[dict[str, str]]
    agent_configs: list[dict[str, str]]
    bundle_sha256: str
    bundle_signature: str


class VerifyBundleRequest(BaseModel):
    """Request payload to verify a portability container."""

    model_config = ConfigDict(frozen=True)

    bundle: PortabilityBundleResponse


class VerifyBundleResponse(BaseModel):
    """Verification outcome of a portability bundle."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    reason: str


class ShredPathRequest(BaseModel):
    """Request payload to directly execute multi-pass physical shredding on a path."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(..., description="Absolute path of file or directory to securely shred")
    passes: int = Field(default=3, ge=1, le=7, description="Number of overwrite passes")


class ShredPathResponse(BaseModel):
    """Result of path shredding."""

    model_config = ConfigDict(frozen=True)

    target_path: str
    files_shredded: int
    bytes_shredded: int
    success: bool
