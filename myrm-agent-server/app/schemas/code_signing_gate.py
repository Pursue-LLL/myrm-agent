"""
[POS] app/schemas/code_signing_gate.py
[INPUT] pydantic, enum
[OUTPUT] SupplyChainTrustPolicyEnum, PackageVerificationVerdictEnum, DeveloperCertificateSchema, PackageManifestEntrySchema, PackageSignRequest, SignedPackageResponse, PackageVerifyRequest, PackageVerifyResponse, TrustPolicyUpdateRequest, TrustPolicyResponse, RevokeCertificateRequest, CodeSigningGateMetricsResponse

Pydantic schemas for Developer Identity Attestation & Agent Package Code Signing Gate Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SupplyChainTrustPolicyEnum(StrEnum):
    """Enterprise supply chain trust enforcement policies."""

    STRICT_ENTERPRISE_ONLY = "STRICT_ENTERPRISE_ONLY"
    VERIFIED_CA_ONLY = "VERIFIED_CA_ONLY"
    ALLOW_COMMUNITY_WARNING = "ALLOW_COMMUNITY_WARNING"
    DENY_ALL = "DENY_ALL"


class PackageVerificationVerdictEnum(StrEnum):
    """Decision verdict for package code signature and supply chain trust."""

    VERIFIED = "VERIFIED"
    UNSIGNED_COMMUNITY = "UNSIGNED_COMMUNITY"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_CERTIFICATE = "EXPIRED_CERTIFICATE"
    REVOKED_CERTIFICATE = "REVOKED_CERTIFICATE"
    TAMPERED_MANIFEST_DIGEST = "TAMPERED_MANIFEST_DIGEST"
    POLICY_REJECTED = "POLICY_REJECTED"


class DeveloperCertificateSchema(BaseModel):
    """Developer real-name certificate attributes and public verification material."""

    developer_id: str = Field(..., min_length=1, max_length=128, description="Developer unique identifier")
    developer_name: str = Field(..., min_length=1, max_length=128, description="Verified legal individual or organization name")
    org_dn: str = Field(..., min_length=1, max_length=256, description="Distinguished Name string")
    issuer_ca: str = Field(..., min_length=1, max_length=128, description="Accredited Certificate Authority")
    cert_serial: str = Field(..., min_length=1, max_length=128, description="Certificate serial number")
    valid_until: float = Field(..., ge=0.0, description="Expiration timestamp (epoch)")
    public_key_pem: str = Field(..., min_length=1, description="Ed25519 Public Key in PEM format")
    is_internal_enterprise: bool = Field(default=False, description="True if developer is internal to organization")


class PackageManifestEntrySchema(BaseModel):
    """Cryptographic digest entry for an individual file asset within an agent/skill package."""

    file_path: str = Field(..., min_length=1, description="Relative path within package")
    sha256_hash: str = Field(..., min_length=64, max_length=64, description="Hexadecimal SHA-256 digest")
    size_bytes: int = Field(..., ge=0, description="Payload file size in bytes")


class PackageSignRequest(BaseModel):
    """Payload to build canonical manifest and sign agent package with developer private key."""

    package_id: str = Field(..., min_length=1, max_length=128, description="Package identifier")
    package_name: str = Field(..., min_length=1, max_length=128, description="Human-readable package name")
    version: str = Field(..., min_length=1, max_length=32, description="Semantic version string")
    files: dict[str, str] = Field(..., min_length=1, description="Map of relative file paths to string/text content")
    private_key_pem: str = Field(..., min_length=1, description="Developer Ed25519 Private Key in PEM format")
    cert_info: DeveloperCertificateSchema | None = Field(default=None, description="Optional certificate metadata to embed")


class SignedPackageResponse(BaseModel):
    """Complete package manifest with attached detached digital signature."""

    package_id: str = Field(..., description="Package identifier")
    package_name: str = Field(..., description="Package name")
    version: str = Field(..., description="Package version")
    manifest_entries: list[PackageManifestEntrySchema] = Field(..., description="List of individual file digests")
    canonical_manifest_digest: str = Field(..., description="Top-level aggregate manifest digest")
    signature_b64: str = Field(..., description="Base64-encoded detached signature")
    cert_info: DeveloperCertificateSchema | None = Field(default=None, description="Attached certificate metadata")


class PackageVerifyRequest(BaseModel):
    """Payload to verify package integrity and supply chain policy compliance."""

    package: SignedPackageResponse = Field(..., description="Signed package descriptor")
    actual_files: dict[str, str] | None = Field(
        default=None, description="Optional payload files to physically verify against manifest"
    )


class PackageVerifyResponse(BaseModel):
    """Outcome of verifying package code signing and supply chain policy."""

    is_allowed: bool = Field(..., description="True if package passes signature and policy gates")
    verdict: PackageVerificationVerdictEnum = Field(..., description="Evaluation verdict code")
    reason: str = Field(..., description="Human-readable verification explanation")
    verified_developer: str | None = Field(default=None, description="Developer name if verified")
    cert_serial: str | None = Field(default=None, description="Certificate serial if present")
    is_enterprise_verified: bool = Field(default=False, description="True if signed by internal enterprise developer")


class TrustPolicyUpdateRequest(BaseModel):
    """Request payload to change active supply chain policy."""

    policy: SupplyChainTrustPolicyEnum = Field(..., description="New enterprise trust policy")


class TrustPolicyResponse(BaseModel):
    """Active enterprise trust policy response."""

    active_policy: SupplyChainTrustPolicyEnum = Field(..., description="Current active policy")


class RevokeCertificateRequest(BaseModel):
    """Payload to revoke a developer certificate."""

    cert_serial: str = Field(..., min_length=1, description="Serial number of certificate to revoke")


class CodeSigningGateMetricsResponse(BaseModel):
    """Cumulative operational metrics for supply chain code signing gate."""

    total_verifications: int = Field(..., ge=0)
    verified_count: int = Field(..., ge=0)
    blocked_untrusted_count: int = Field(..., ge=0)
    tampered_count: int = Field(..., ge=0)
    signature_failures: int = Field(..., ge=0)
