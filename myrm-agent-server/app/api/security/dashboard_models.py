"""Pydantic models for the security dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SecurityAlert(_CamelModel):
    id: int
    severity: str
    rule_id: str
    rule_description: str
    state: str
    created_at: datetime
    html_url: str


class DependabotPR(_CamelModel):
    number: int
    title: str
    state: str
    labels: list[str]
    html_url: str
    created_at: datetime


class SecurityMetrics(_CamelModel):
    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    open_dependabot_prs: int
    security_prs: int


class SecurityDashboard(_CamelModel):
    metrics: SecurityMetrics
    recent_alerts: list[SecurityAlert]
    recent_prs: list[DependabotPR]
    sbom_available: bool
    data_source: Literal["github", "control_plane", "merged"] = "github"


class SecuritySetupHints(_CamelModel):
    deploy_mode: str
    is_sandbox: bool
    cp_ingress_configured: bool
    github_token_configured: bool
    webhook_tenant_id: str | None = None
    webhook_url: str | None = None
    cp_webhook_secret_env: str = Field(
        default="MYRM_CP_GITHUB_WEBHOOK_SECRET",
        description="Control plane env var for GitHub webhook HMAC secret",
    )


class RateLimitStatusItem(_CamelModel):
    user_id: str
    resource: str
    current: int
    max: int
    remaining: int
    window_seconds: int


class SecurityRateLimitsResponse(_CamelModel):
    items: list[RateLimitStatusItem]
    is_live: bool = False


class PlatformAuditEvent(_CamelModel):
    event_type: str
    timestamp: str
    severity: str
    user_id: str | None = None
    sandbox_id: str | None = None
    resource: str | None = None
    action: str = ""
    result: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    ip_address: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    traffic_class: str | None = None
    source: Literal["control_plane", "auth"] = "control_plane"


class PlatformAuditLogsResponse(_CamelModel):
    events: list[PlatformAuditEvent]
    total: int
    is_live: bool = False


class PlatformAuditTimeSeriesPoint(_CamelModel):
    timestamp: str
    total: int
    success: int
    failed: int


class PlatformAuditTopIp(_CamelModel):
    ip_address: str
    request_count: int


class PlatformAuditEventCount(_CamelModel):
    event_type: str
    count: int


class PlatformAuditSuccessFailed(_CamelModel):
    success: int
    failed: int


class PlatformAuditStatsResponse(_CamelModel):
    time_series: list[PlatformAuditTimeSeriesPoint]
    top_ips: list[PlatformAuditTopIp]
    event_distribution: list[PlatformAuditEventCount]
    success_vs_failed: PlatformAuditSuccessFailed
    total_events: int
    time_range_hours: int
    is_live: bool = False
