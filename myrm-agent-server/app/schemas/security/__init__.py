"""[POS]
Security dashboard shared DTOs.

[INPUT]
- .dashboard: Dashboard domain schemas

[OUTPUT]
- Re-exported schema types for security API consumers
"""

from app.schemas.security.dashboard import (
    DependabotPR,
    PlatformAuditEvent,
    PlatformAuditEventCount,
    PlatformAuditLogsResponse,
    PlatformAuditStatsResponse,
    PlatformAuditSuccessFailed,
    PlatformAuditTimeSeriesPoint,
    PlatformAuditTopIp,
    RateLimitStatusItem,
    SecurityAlert,
    SecurityDashboard,
    SecurityMetrics,
    SecurityRateLimitsResponse,
    SecuritySetupHints,
)

__all__ = [
    "DependabotPR",
    "PlatformAuditEvent",
    "PlatformAuditEventCount",
    "PlatformAuditLogsResponse",
    "PlatformAuditStatsResponse",
    "PlatformAuditSuccessFailed",
    "PlatformAuditTimeSeriesPoint",
    "PlatformAuditTopIp",
    "RateLimitStatusItem",
    "SecurityAlert",
    "SecurityDashboard",
    "SecurityMetrics",
    "SecurityRateLimitsResponse",
    "SecuritySetupHints",
]
