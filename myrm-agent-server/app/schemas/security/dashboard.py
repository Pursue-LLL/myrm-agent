"""Security dashboard shared Pydantic DTOs (API + services).

[INPUT]
- pydantic::BaseModel (POS: schema 校验)

[OUTPUT]
- SecurityDashboard, PlatformAuditLogsResponse, SecurityRateLimitsResponse, etc.

[POS]
schemas 层安全仪表盘契约。禁止 services 依赖 app.api 获取 DTO。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.security.base import CamelModel


class SecurityAlert(CamelModel):
    id: int
    severity: str
    rule_id: str
    rule_description: str
    state: str
    created_at: datetime
    html_url: str


class DependabotPR(CamelModel):
    number: int
    title: str
    state: str
    labels: list[str]
    html_url: str
    created_at: datetime


class SecurityMetrics(CamelModel):
    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    open_dependabot_prs: int
    security_prs: int


class SecurityDashboard(CamelModel):
    metrics: SecurityMetrics
    recent_alerts: list[SecurityAlert]
    recent_prs: list[DependabotPR]
    sbom_available: bool
    data_source: Literal["github", "control_plane", "merged"] = "github"


class SecuritySetupHints(CamelModel):
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


class RateLimitStatusItem(CamelModel):
    user_id: str
    resource: str
    current: int
    max: int
    remaining: int
    window_seconds: int


class SecurityRateLimitsResponse(CamelModel):
    items: list[RateLimitStatusItem]
    is_live: bool = False


class PlatformAuditEvent(CamelModel):
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


class PlatformAuditLogsResponse(CamelModel):
    events: list[PlatformAuditEvent]
    total: int
    is_live: bool = False


class PlatformAuditTimeSeriesPoint(CamelModel):
    timestamp: str
    total: int
    success: int
    failed: int


class PlatformAuditTopIp(CamelModel):
    ip_address: str
    request_count: int


class PlatformAuditEventCount(CamelModel):
    event_type: str
    count: int


class PlatformAuditSuccessFailed(CamelModel):
    success: int
    failed: int


class PlatformAuditStatsResponse(CamelModel):
    time_series: list[PlatformAuditTimeSeriesPoint]
    top_ips: list[PlatformAuditTopIp]
    event_distribution: list[PlatformAuditEventCount]
    success_vs_failed: PlatformAuditSuccessFailed
    total_events: int
    time_range_hours: int
    is_live: bool = False


class DualTrackAuditEntryItem(CamelModel):
    entry_id: str
    session_id: str
    agent_id: str
    tool_name: str
    intent_summary: str
    raw_intent_args: dict[str, object]
    rule_name: str
    state: str
    outcome: str
    is_human_take_the_wheel: bool
    created_at: str
    completed_at: str | None = None
    latency_ms: float
    output_length: int
    error_message: str | None = None


class RuleTriggerHitItem(CamelModel):
    rule_name: str
    trigger_count: int
    refused_count: int
    permitted_count: int
    failed_count: int
    refusal_rate: float
    sample_targets: list[str]


class DualTrackAuditStatsResponse(CamelModel):
    total_entries: int
    permitted_count: int
    refused_count: int
    failed_count: int
    human_take_the_wheel_count: int
    compliance_rate: float
    avg_latency_ms: float
    top_rules_triggered: list[RuleTriggerHitItem]
