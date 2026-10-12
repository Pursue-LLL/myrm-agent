"""Pydantic DTO schemas for Third-Party Asset License Compliance and Copyleft Gating.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for license evaluations, asset registration, inventory auditing,
  and CycloneDX-compliant SBOM exports.

[POS]
- Server schemas. Exposes typed contracts for license compliance gating endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LicenseMetadataDto(BaseModel):
    """SPDX normalized license metadata DTO."""

    model_config = ConfigDict(extra="forbid")

    spdx_id: str = Field(..., description="Canonical SPDX identifier (e.g. MIT, AGPL-3.0-only)")
    raw_name: str = Field(..., description="Human readable license name")
    risk_tier: str = Field(..., description="Risk tier: PERMISSIVE, WEAK_COPYLEFT, STRONG_COPYLEFT, etc.")
    is_copyleft: bool = Field(..., description="Whether license enforces copyleft sharing obligations")
    commercial_friendly: bool = Field(..., description="Whether license is freely reusable in commercial SaaS")
    description: str = Field(default="", description="Brief legal overview of the license")


class AssetLicenseDescriptorDto(BaseModel):
    """Registered asset license descriptor DTO."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., description="Unique asset identifier")
    asset_type: str = Field(..., description="Asset type: skill, mcp_server, npm_package, etc.")
    detected_license: LicenseMetadataDto = Field(..., description="Normalized detected license")
    license_file_path: str | None = Field(default=None, description="Local manifest or license file path")
    package_url: str | None = Field(default=None, description="Package URL (purl) identifier if known")


class EvaluateLicenseRequest(BaseModel):
    """Request payload to preflight evaluate an asset license before installation."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., description="Asset identifier to evaluate")
    asset_type: str = Field(default="skill", description="Type of asset (skill, mcp_server, package)")
    declared_license: str | None = Field(
        default=None, description="Declared license name or SPDX expression"
    )
    environment: str = Field(
        default="CLOUD_COMMERCIAL",
        description="Target deployment environment (LOCAL_DESKTOP or CLOUD_COMMERCIAL)",
    )
    allow_override: bool = Field(
        default=False, description="Whether to exercise administrative policy risk override"
    )


class EvaluateLicenseResponse(BaseModel):
    """Evaluation verdict response indicating admission or gating blocking."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(..., description="ALLOWED, WARNING_PROCEED, or BLOCKED_*")
    asset_id: str = Field(..., description="Asset identifier")
    detected_license: LicenseMetadataDto = Field(..., description="Detected license metadata")
    environment: str = Field(..., description="Evaluated environment")
    reason: str = Field(..., description="Detailed legal and compliance rationale")
    can_override: bool = Field(..., description="Whether decision can be overridden by admin")
    audit_notes: str = Field(default="", description="Audit log annotations")


class RegisterAssetRequest(BaseModel):
    """Request payload to register and scan a third-party asset into the inventory ledger."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., description="Asset identifier")
    asset_type: str = Field(default="skill", description="Asset type")
    declared_license: str | None = Field(default=None, description="Declared license string")
    manifest_path: str | None = Field(default=None, description="Local path to manifest or LICENSE file")
    package_url: str | None = Field(default=None, description="Package URL (purl)")


class LicenseInventorySummaryDto(BaseModel):
    """Aggregated compliance inventory summary across all tracked third-party assets."""

    model_config = ConfigDict(extra="forbid")

    total_assets: int = Field(..., description="Total count of registered assets")
    permissive_count: int = Field(..., description="Count of permissive-licensed assets")
    weak_copyleft_count: int = Field(..., description="Count of weak-copyleft assets")
    strong_copyleft_count: int = Field(..., description="Count of strong viral copyleft assets")
    unknown_count: int = Field(..., description="Count of unclassified licenses")
    has_blocking_violations: bool = Field(
        ..., description="True if any asset violates strict deployment policy"
    )
    assets: list[AssetLicenseDescriptorDto] = Field(..., description="Detailed list of tracked assets")


class CycloneDxLicenseRecordDto(BaseModel):
    """CycloneDX SBOM compliant license record."""

    model_config = ConfigDict(extra="forbid")

    bom_ref: str = Field(..., description="BOM component reference")
    asset_type: str = Field(..., description="Asset classification")
    license_id: str = Field(..., description="SPDX ID")
    license_name: str = Field(..., description="Full license name")
    risk_tier: str = Field(..., description="Risk tier string")
    copyleft: str = Field(..., description="'true' or 'false'")
    commercial_friendly: str = Field(..., description="'true' or 'false'")
    purl: str | None = Field(default=None, description="Package URL if available")
