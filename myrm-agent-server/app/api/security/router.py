"""
Security Dashboard API

Aggregates GitHub Security API and control-plane webhook-backed alerts.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.security.dashboard_models import (
    DependabotPR,
    PlatformAuditLogsResponse,
    PlatformAuditStatsResponse,
    SecurityAlert,
    SecurityDashboard,
    SecurityRateLimitsResponse,
    SecuritySetupHints,
)
from app.config.settings import settings as _settings
from app.services.security.cp_rate_limit import fetch_cp_rate_limits
from app.services.security.dashboard_settings import load_monitored_github_repos
from app.services.security.github_supplement import fetch_dependabot_prs_for_repo
from app.services.security.merged_dashboard import build_security_dashboard, build_setup_hints
from app.services.security.platform_audit import (
    export_platform_audit_logs,
    fetch_platform_audit_logs,
    fetch_platform_audit_stats,
)

logger = logging.getLogger(__name__)

GITHUB_TOKEN = _settings.services.github_token.get_secret_value()
DEFAULT_REPO = "Pursue-LLL/myrm-agent"

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/dashboard", response_model=SecurityDashboard)
async def get_security_dashboard() -> SecurityDashboard:
    """Security dashboard: GitHub (local) or CP alerts + GitHub PR/SBOM (sandbox)."""
    return await build_security_dashboard()


@router.get("/setup-hints", response_model=SecuritySetupHints)
async def get_security_setup_hints() -> SecuritySetupHints:
    """Webhook URL and env hints for SaaS (tenant id = platform user id)."""
    return await build_setup_hints()


@router.get("/rate-limits", response_model=SecurityRateLimitsResponse)
async def get_security_rate_limits() -> SecurityRateLimitsResponse:
    """Platform rate limits from control plane (sandbox only)."""
    return await fetch_cp_rate_limits()


@router.get("/alerts", response_model=list[SecurityAlert])
async def get_security_alerts(
    severity: str | None = None,
    state: str | None = "open",
) -> list[SecurityAlert]:
    dashboard = await build_security_dashboard()
    alerts = dashboard.recent_alerts
    if severity:
        alerts = [alert for alert in alerts if alert.severity == severity]
    if state:
        alerts = [alert for alert in alerts if alert.state == state]
    return alerts


@router.get("/audit/logs", response_model=PlatformAuditLogsResponse)
async def get_platform_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
) -> PlatformAuditLogsResponse:
    """Platform audit logs: control plane (sandbox) or local auth JSONL."""
    return await fetch_platform_audit_logs(limit=limit)


@router.get("/audit/stats", response_model=PlatformAuditStatsResponse)
async def get_platform_audit_stats(
    hours: int = Query(24, ge=1, le=168),
) -> PlatformAuditStatsResponse:
    """Aggregated platform audit statistics for the security dashboard."""
    return await fetch_platform_audit_stats(hours=hours)


@router.get("/audit/export")
async def export_platform_audit(
    format: Literal["csv", "json"] = Query("csv"),
) -> Response:
    """Export platform audit logs as CSV or JSON."""
    return await export_platform_audit_logs(export_format=format)


@router.get("/dependabot-prs", response_model=list[DependabotPR])
async def get_dependabot_prs() -> list[DependabotPR]:
    try:
        token = GITHUB_TOKEN.strip() or None
        monitored = await load_monitored_github_repos()
        repo = monitored[0] if monitored else DEFAULT_REPO
        return await fetch_dependabot_prs_for_repo(repo, token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"GitHub API error: {exc.response.text}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Dependabot PRs: {exc}") from exc
