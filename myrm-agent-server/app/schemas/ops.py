"""Ops Aggregated Snapshot Pydantic DTO Schemas.

[INPUT]
- (none — leaf schema module, depends only on pydantic/stdlib)

[OUTPUT]
- OpsAggregatedSnapshot and its structured sub-models (System, Liveness, Resources, Channels, Governance, UsageRadar, Memory, DoctorSummary)

[POS]
Data contract for GET /api/v1/ops/snapshot operations.
Provides single-request full-spectrum observability for Control Plane, WebUI/Desktop, and CLI tools.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class OpsSystemInfo(BaseModel):
    """System runtime & deployment identity."""

    app_name: str
    app_version: str
    deploy_mode: str
    os: str
    python_version: str
    uptime_seconds: float
    timestamp_utc: str


class OpsLivenessInfo(BaseModel):
    """Agent execution gateway and liveness state."""

    state: Literal["idle", "busy", "degraded", "draining"]
    active_sessions_count: int
    active_sessions: list[dict[str, object]] = Field(default_factory=list)
    available_slots: int
    max_concurrent: int
    is_draining: bool = False
    pending_outbound_count: int = 0


class OpsResourceInfo(BaseModel):
    """Memory, process RSS, and execution unit cache metrics."""

    process_rss_mb: float | None = None
    memory_level: str
    memory_percent: float
    idle_reclaim_timeout_seconds: float
    warm_execution_units: int
    reclaimed_execution_units: int


class OpsChannelInfo(BaseModel):
    """Channel gateway registrations and individual statuses."""

    total_channels: int
    channels: dict[str, dict[str, object]] = Field(default_factory=dict)
    has_degraded_channel: bool = False


class OpsGovernanceInfo(BaseModel):
    """Human-gated governance, cron runs, and active goals rollup."""

    cron_failures_24h: int = 0
    pending_approvals: int = 0
    unread_notifications: int = 0
    active_goals: int = 0
    extension_connected: bool = False


class OpsUsageRadarInfo(BaseModel):
    """High-level usage radar across all chats."""

    total_calls: int = 0
    total_tokens: int = 0
    total_usd: float = 0.0


class OpsMemoryInfo(BaseModel):
    """Content-free memory command center health overview."""

    health_status: Literal["healthy", "degraded", "critical", "unknown"]
    storage_mode: str
    event_count: int = 0
    failed_event_count: int = 0
    queue_backlog: int = 0


class OpsDoctorSummaryInfo(BaseModel):
    """Harness and Server health probe diagnostics summary."""

    harness_total: int = 0
    harness_passed: int = 0
    harness_failed: int = 0
    server_total: int = 0
    server_passed: int = 0
    server_failed: int = 0
    status: Literal["pass", "warn", "fail"] = "pass"
    issues: list[dict[str, object]] = Field(default_factory=list)


class OpsAggregatedSnapshot(BaseModel):
    """Full-spectrum operational snapshot of the single-agent runtime."""

    system: OpsSystemInfo
    liveness: OpsLivenessInfo
    resources: OpsResourceInfo
    channels: OpsChannelInfo
    governance: OpsGovernanceInfo
    usage_radar: OpsUsageRadarInfo
    memory: OpsMemoryInfo
    doctor_summary: OpsDoctorSummaryInfo | None = None
