"""Pydantic schemas for NVIDIA SkillSpector Level Skill Supply Chain Security Scanner.

[INPUT]
- None (Self-contained schema representations for skill security scanning)

[OUTPUT]
- SkillScanRequest, SecurityFindingResponse, SkillScanReportResponse

[POS]
- app.schemas.skill_spector_scanner
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SkillScanRequest(BaseModel):
    """Payload to scan an AI skill package for prompt injection, taint, and supply chain risks."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(..., min_length=1, max_length=128, description="Unique skill identifier")
    skill_version: str = Field(default="1.0.0", max_length=32, description="Semantic version string")
    files: dict[str, str] = Field(..., description="Mapping of relative file path to file content")
    declared_permissions: list[str] = Field(
        default_factory=list,
        description="Permissions declared in manifest (e.g. network, fs_read)",
    )


class SecurityFindingResponse(BaseModel):
    """Vulnerability or security hazard identified by the scanner."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    category: str
    severity: str
    file_name: str
    line_number: int
    matched_content: str
    description: str


class SandboxProfileResponse(BaseModel):
    """Synthesized least-privilege sandbox profile."""

    model_config = ConfigDict(extra="forbid")

    network_egress_allowed: bool
    allowed_domains: list[str]
    read_only_filesystem: bool
    allowed_write_paths: list[str]
    capabilities_dropped: list[str]


class SkillScanReportResponse(BaseModel):
    """Comprehensive skill security evaluation report."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    skill_version: str
    safety_rating: str
    is_shield_verified: bool
    findings: list[SecurityFindingResponse]
    sandbox_profile: SandboxProfileResponse
    scanned_at: float


class RevokeSkillRequest(BaseModel):
    """Payload to revoke and decommission a malicious or vulnerable skill."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(..., min_length=1, max_length=128, description="Skill ID to revoke")
    reason: str = Field(..., min_length=1, max_length=1000, description="Reason or CVE reference for revocation")


class RevocationStatusResponse(BaseModel):
    """Status indicating whether a skill is revoked."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    is_revoked: bool
    reason: str | None = None


class RevocationListResponse(BaseModel):
    """Collection of revoked skill IDs and reasons."""

    model_config = ConfigDict(extra="forbid")

    revoked_skills: dict[str, str]
    total: int
