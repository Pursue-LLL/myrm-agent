"""Pydantic schemas for Marketplace Manifest Source Pinning & Capability Contract.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for marketplace package manifests, capability contracts,
  organization admission policies, and gate evaluation responses.

[POS]
- Server schemas. Exposes typed contracts for client marketplace UI and enterprise admin controls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CapabilityContractDto(BaseModel):
    """Declared capabilities introduced upon package installation."""

    model_config = ConfigDict(extra="forbid")

    provides_tools: list[str] = Field(
        default_factory=list, description="Tool names provided by package"
    )
    provides_hooks: list[str] = Field(
        default_factory=list, description="Agent lifecycle hooks provided by package"
    )
    provides_middleware: list[str] = Field(
        default_factory=list, description="Agent middlewares introduced by package"
    )
    requires_env: list[str] = Field(
        default_factory=list, description="Required environment variables"
    )
    declared_mcp_servers: list[str] = Field(
        default_factory=list, description="Declared embedded MCP servers"
    )


class MarketplaceManifestItemDto(BaseModel):
    """Declarative marketplace package manifest entry with source pinning."""

    model_config = ConfigDict(extra="forbid")

    package_id: str = Field(..., description="Unique package identifier")
    name: str = Field(..., description="Display package name")
    version: str = Field(..., description="Semantic package version")
    repo_url: str = Field(..., description="Secure Git repository clone URL")
    source_sha: str = Field(
        ..., description="Immutable 40-char SHA-1 or 64-char SHA-256 commit/release hash"
    )
    tier: str = Field(
        default="COMMUNITY", description="Classification tier: OFFICIAL, VERIFIED, COMMUNITY, UNVERIFIED"
    )
    requires_host: str = Field(
        default=">=0.1.0", description="Minimum host framework version required"
    )
    platforms: list[str] = Field(
        default_factory=lambda: ["all"], description="Supported platforms: macos, linux, windows, all"
    )
    capabilities: CapabilityContractDto = Field(
        default_factory=CapabilityContractDto, description="Declared capabilities"
    )
    publisher: str = Field(default="community", description="Publisher or author handle")


class AdmissionPolicyDto(BaseModel):
    """Organization-level admission allowlist policy."""

    model_config = ConfigDict(extra="forbid")

    allowed_sources: list[str] = Field(
        default_factory=list, description="Allowed repository URL prefixes or SHA digests"
    )
    allowed_tiers: list[str] = Field(
        default_factory=list, description="Allowed tier strings: OFFICIAL, VERIFIED, etc."
    )
    disallowed_capabilities: list[str] = Field(
        default_factory=list, description="Forbidden tool, hook, or middleware identifiers"
    )
    enforce_strict_pinning: bool = Field(
        default=True, description="Enforce that source_sha is a valid immutable hex digest"
    )


class AdmissionVerdictDto(BaseModel):
    """Outcome of package admission gate evaluation."""

    model_config = ConfigDict(extra="forbid")

    is_admitted: bool = Field(..., description="Whether package is authorized for installation")
    package_id: str = Field(..., description="Evaluated package ID")
    reason: str = Field(..., description="Detailed explanation of admission outcome")
    violations: list[str] = Field(default_factory=list, description="Specific policy violations")


class ValidateManifestRequest(BaseModel):
    """Payload to validate a marketplace manifest's source pinning and contract."""

    model_config = ConfigDict(extra="forbid")

    manifest: MarketplaceManifestItemDto = Field(..., description="Package manifest to validate")
    target_platform: str = Field(default="all", description="Current operating system platform")


class ValidateManifestResponse(BaseModel):
    """Validation response."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="Whether source pinning and schema are valid")
    platform_supported: bool = Field(..., description="Whether platform is supported")
    error_message: str | None = Field(default=None, description="Validation failure details if invalid")


class EvaluateAdmissionRequest(BaseModel):
    """Payload to evaluate package admission against active organization policy."""

    model_config = ConfigDict(extra="forbid")

    manifest: MarketplaceManifestItemDto = Field(..., description="Target package manifest")


class EvaluateAdmissionResponse(BaseModel):
    """Admission gate evaluation response."""

    model_config = ConfigDict(extra="forbid")

    verdict: AdmissionVerdictDto = Field(..., description="Gate evaluation verdict")
    is_admitted: bool = Field(..., description="Convenience flag: True if admitted")


class UpdateAdmissionPolicyRequest(BaseModel):
    """Payload for organization administrators to update admission allowlist policies."""

    model_config = ConfigDict(extra="forbid")

    policy: AdmissionPolicyDto = Field(..., description="New admission policy configuration")
