"""Pydantic schemas for High-Risk Surface CI Gate and Skill Change SecOps Audit.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for path surface diff analysis, skill capability scanning,
  and cryptographic manifest signing and verification.

[POS]
- Server schemas. Exposes typed contracts for automated PR labeling,
  multi-party review gating, and skill supply-chain integrity verification.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class SurfaceMatchDto(BaseModel):
    """Details of a single file path matching a high-risk surface rule."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Normalized repository relative file path")
    category: str = Field(..., description="Risk category: public_api, auth_security, mcp_config, etc.")
    suggested_label: str = Field(..., description="Automated GitHub label: ⚠️ risk:high-surface, etc.")
    reason: str = Field(..., description="Security justification for classification")


class ScanSurfacesRequest(BaseModel):
    """Payload containing a list of modified file paths in a PR or commit."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(..., description="List of file paths modified in the commit or pull request")


class ScanSurfacesResponse(BaseModel):
    """Result of automated surface risk scanning and label recommendations."""

    model_config = ConfigDict(extra="forbid")

    total_files_scanned: int = Field(..., description="Total count of unique paths scanned")
    high_risk_detected: bool = Field(..., description="True if any high-risk surface rule was triggered")
    requires_multi_party_review: bool = Field(
        ..., description="True if change mandates at least two security maintainer approvals"
    )
    applied_labels: list[str] = Field(default_factory=list, description="Automated labels for GitHub PR tagging")
    matches: list[SurfaceMatchDto] = Field(default_factory=list, description="Matched surface rule details")
    scanned_at: float = Field(default_factory=time.time, description="Unix timestamp of scan")


class SkillIntegrityManifestDto(BaseModel):
    """Cryptographic manifest binding a skill definition to its author and permissions."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Identifier name of the skill")
    skill_version: str = Field(..., description="Semantic version string")
    content_hash: str = Field(..., description="SHA-256 fingerprint of skill content")
    declared_permissions: list[str] = Field(
        default_factory=list, description="Explicit permissions requested by skill"
    )
    signature: str = Field(..., description="HMAC-SHA256 signature string")
    signed_by: str = Field(..., description="Identity or role of signer")
    signed_at: float = Field(default_factory=time.time, description="Unix timestamp of signing")


class SignSkillManifestRequest(BaseModel):
    """Request payload to generate a signed integrity manifest for a skill."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Identifier name of the skill")
    skill_version: str = Field(..., description="Semantic version of the skill")
    content: str = Field(..., description="Full content of the SKILL.md file")
    secret_key: str = Field(..., description="Shared or authority signing secret key")
    signed_by: str = Field(default="security-team", description="Signer identity")


class VerifySkillRequest(BaseModel):
    """Request payload to audit and verify a skill before mounting."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Identifier name of the skill")
    content: str = Field(..., description="Full content of the SKILL.md file to inspect")
    manifest: SkillIntegrityManifestDto | None = Field(
        default=None, description="Optional manifest to verify against"
    )
    secret_key: str | None = Field(
        default=None, description="Optional secret key to verify signature authenticity"
    )


class VerifySkillResponse(BaseModel):
    """Audit report examining a SKILL.md before execution or mounting."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Skill name inspected")
    is_valid: bool = Field(..., description="True if signature and permissions match without tampering")
    content_hash: str = Field(..., description="Calculated SHA-256 content hash")
    detected_permissions: list[str] = Field(
        default_factory=list, description="Statically detected sensitive permissions"
    )
    unapproved_permissions: list[str] = Field(
        default_factory=list, description="Permissions detected but not declared in manifest"
    )
    signature_verified: bool = Field(..., description="True if cryptographic signature was verified")
    requires_user_consent: bool = Field(
        ..., description="True if dangerous permissions require explicit UI confirmation"
    )
    violations: list[str] = Field(default_factory=list, description="Security policy violations found")
