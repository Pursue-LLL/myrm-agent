"""Build the security dashboard (control-plane alerts + optional GitHub supplement)."""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from app.api.security.dashboard_models import (
    SecurityAlert,
    SecurityDashboard,
    SecurityMetrics,
    SecuritySetupHints,
)
from app.config.deploy_mode import get_deploy_mode, is_sandbox
from app.config.settings import settings
from app.services.security.cp_security_dashboard import (
    fetch_cp_security_payload,
    fetch_cp_webhook_tenant_id,
    map_cp_dashboard,
)
from app.services.security.github_supplement import fetch_github_supplement, repos_from_cp_payload
from app.services.security.github_full import build_github_dashboard

logger = logging.getLogger(__name__)

_DEFAULT_REPO = "Pursue-LLL/myrm-agent"


def _github_token() -> str | None:
    raw = settings.services.github_token.get_secret_value().strip()
    return raw or None


async def _merge_cp_with_github(
    cp_dashboard: SecurityDashboard,
    cp_payload: dict[str, object],
    token: str | None,
) -> SecurityDashboard:
    repos = repos_from_cp_payload(cp_payload, fallback_default=False)
    recent_prs, pr_metrics, sbom_available = await fetch_github_supplement(repos, token)

    metrics = SecurityMetrics(
        total_alerts=cp_dashboard.metrics.total_alerts,
        critical_count=cp_dashboard.metrics.critical_count,
        high_count=cp_dashboard.metrics.high_count,
        medium_count=cp_dashboard.metrics.medium_count,
        low_count=cp_dashboard.metrics.low_count,
        open_dependabot_prs=pr_metrics.open_dependabot_prs,
        security_prs=pr_metrics.security_prs,
    )
    return SecurityDashboard(
        metrics=metrics,
        recent_alerts=cp_dashboard.recent_alerts,
        recent_prs=recent_prs,
        sbom_available=sbom_available,
        data_source="merged",
    )


async def build_security_dashboard() -> SecurityDashboard:
    """Resolve dashboard for local (GitHub) or sandbox (CP + GitHub supplement)."""
    cp_payload = await fetch_cp_security_payload()
    token = _github_token()

    if cp_payload is not None:
        cp_dashboard = map_cp_dashboard(cp_payload)
        if token:
            return await _merge_cp_with_github(cp_dashboard, cp_payload, token)
        return SecurityDashboard(
            metrics=cp_dashboard.metrics,
            recent_alerts=cp_dashboard.recent_alerts,
            recent_prs=[],
            sbom_available=False,
            data_source="control_plane",
        )

    try:
        return await build_github_dashboard(_DEFAULT_REPO, token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"GitHub API error: {exc.response.text}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch security data: {exc}") from exc


async def build_setup_hints() -> SecuritySetupHints:
    ingress = settings.cp_public_ingress_url.strip().rstrip("/")
    token = _github_token()
    deploy_mode = get_deploy_mode().value
    sandbox = is_sandbox()

    webhook_tenant_id: str | None = None
    webhook_url: str | None = None

    if sandbox and ingress:
        payload = await fetch_cp_security_payload()
        if payload is not None:
            raw_tenant = payload.get("tenant_id")
            if isinstance(raw_tenant, str) and raw_tenant.strip():
                webhook_tenant_id = raw_tenant.strip()
        if not webhook_tenant_id:
            webhook_tenant_id = await fetch_cp_webhook_tenant_id()
        if webhook_tenant_id:
            webhook_url = f"{ingress}/api/security/webhook/{webhook_tenant_id}"

    return SecuritySetupHints(
        deploy_mode=deploy_mode,
        is_sandbox=sandbox,
        cp_ingress_configured=bool(ingress),
        github_token_configured=bool(token),
        webhook_tenant_id=webhook_tenant_id,
        webhook_url=webhook_url,
    )
