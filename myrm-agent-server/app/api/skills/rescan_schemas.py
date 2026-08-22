"""Schemas for skill supply chain rescan and advisory governance endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RescanTriggerRequest(BaseModel):
    """Request to trigger a skill rescan."""

    skill_id: str | None = Field(default=None, description="Optional single skill name to rescan")
    enable_online_osv: bool = Field(default=True, description="Whether to query OSV API")
    auto_quarantine: bool = Field(
        default=True, description="Whether to disable skills with critical vulnerabilities"
    )


class AdvisoryAckRequest(BaseModel):
    """Request to acknowledge a security advisory."""

    advisory_id: str = Field(..., description="Vulnerability/advisory ID (e.g. MAL-2021-001, GHSA-xxxx)")
    package_name: str = Field(..., description="Package name (e.g. ua-parser-js)")
    reason: str = Field(default="", description="Reason for acknowledgment / dismissal")
    acked_by: str = Field(default="user", description="Identifier of the user or admin")


class AdvisoryUnackRequest(BaseModel):
    """Request to un-acknowledge / reinstate a security advisory."""

    advisory_id: str = Field(..., description="Vulnerability/advisory ID")
    package_name: str = Field(..., description="Package name")


class AdvisoryAckResponse(BaseModel):
    """Response representing an acknowledged advisory."""

    advisory_id: str
    package_name: str
    reason: str
    acked_at: float
    acked_by: str


class SkillRescanItemResponse(BaseModel):
    """Summary of rescan for one skill."""

    skill_name: str
    recommendation: str
    is_clean: bool
    has_critical_or_malware: bool
    quarantined: bool
    summary: str
    declared_dependencies_count: int
    unacked_advisories_count: int
    acked_advisories_count: int
    findings_count: int


class RescanReportResponse(BaseModel):
    """Complete report response of a rescan run."""

    total_scanned: int
    clean_count: int
    quarantined_count: int
    items: list[SkillRescanItemResponse]
