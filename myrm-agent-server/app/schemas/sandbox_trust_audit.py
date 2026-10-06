"""Pydantic schemas for Sandbox Trust Transparency and Security Isolation Audit Card API.

[INPUT]
Standard library datetime, pydantic BaseModel and Field.

[OUTPUT]
SandboxIsolationGrade, NetworkEgressAuditSummary, SandboxTrustAuditCardResponse.

[POS]
Schema definitions for runtime sandbox trust and egress policy audit reporting.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProbeCheckItemResponse(BaseModel):
    """Result of an individual security containment check."""

    check_id: str
    category: str
    description: str
    status: str
    details: str


class SandboxHealthAuditRequest(BaseModel):
    """Payload to trigger an in-situ sandbox containment health scan."""

    environment_id: str = Field(default="default_sandbox", description="Sandbox runtime ID")
    isolation_level: str = Field(
        default="cloud_dedicated_sandbox",
        description="Isolation tier: 'cloud_dedicated_sandbox', 'local_restricted_container', 'host_direct_full_trust'",
    )
    mounted_paths: list[str] = Field(
        default_factory=list, description="List of filesystem mount paths bound into the sandbox"
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict, description="Environment variables exposed inside the sandbox"
    )
    is_root: bool = Field(default=False, description="Whether execution runs as root uid 0")
    egress_monitored: bool = Field(
        default=True, description="Whether outbound network traffic is screened by Sentinel"
    )


class SandboxHealthAuditReportResponse(BaseModel):
    """Report detailing sandbox health checks and escape resistance score."""

    report_id: str
    environment_id: str
    isolation_level: str
    checks: list[ProbeCheckItemResponse]
    passed: bool
    score: int
    timestamp: datetime


class GetTrustBadgeRequest(BaseModel):
    """Query payload to calculate dynamic trust level badge."""

    isolation_level: str = Field(
        default="cloud_dedicated_sandbox",
        description="Isolation tier: 'cloud_dedicated_sandbox', 'local_restricted_container', 'host_direct_full_trust'",
    )
    audit_score: int = Field(default=100, ge=0, le=100, description="Audit health score 0-100")


class SandboxTrustBadgeResponse(BaseModel):
    """Visual trust badge for UI headers and status bars."""

    isolation_level: str
    trust_grade: str
    trust_score: int
    summary: str
    badge_label: str
    color_hex: str


class GetBoundaryCardRequest(BaseModel):
    """Query payload to generate permission boundary inspection card."""

    environment_id: str = Field(default="default_sandbox", description="Sandbox runtime ID")
    isolation_level: str = Field(
        default="cloud_dedicated_sandbox",
        description="Isolation tier: 'cloud_dedicated_sandbox', 'local_restricted_container', 'host_direct_full_trust'",
    )
    allowed_paths: list[str] | None = Field(
        default=None, description="Optional custom allowed path list"
    )


class PermissionBoundaryCardResponse(BaseModel):
    """Interactive permission hot-boundary transparency card."""

    card_id: str
    environment_id: str
    isolation_level: str
    allowed_paths: list[str]
    denied_paths: list[str]
    egress_policy: str
    active_guards: list[str]
    generated_at: datetime
