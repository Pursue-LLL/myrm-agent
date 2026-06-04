"""Fetch SaaS security dashboard from control plane (webhook-backed alerts)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.api.security.dashboard_models import (
    SecurityAlert,
    SecurityDashboard,
    SecurityMetrics,
)
from app.config.deploy_mode import is_sandbox
from app.config.settings import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 8.0


def get_cp_api_base() -> str | None:
    ingress = settings.cp_public_ingress_url.strip().rstrip("/")
    return ingress or None


def get_cp_request_headers() -> dict[str, str] | None:
    cp = settings.control_plane
    token = cp.telemetry_token.get_secret_value().strip()
    sandbox_id = cp.sandbox_id.strip()
    if not token or not sandbox_id:
        return None
    return {
        "X-Telemetry-Token": token,
        "X-Sandbox-Id": sandbox_id,
    }


def _parse_dt(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return datetime.now(UTC)


def _severity_str(value: object) -> str:
    if value is None:
        return "unknown"
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value)


def map_cp_dashboard(payload: dict[str, Any]) -> SecurityDashboard:
    metrics_raw = payload.get("metrics") or {}
    recent = payload.get("recent_alerts") or []

    recent_alerts = [
        SecurityAlert(
            id=int(item.get("id") or item.get("github_alert_id") or 0),
            severity=_severity_str(item.get("severity")),
            rule_id=str(item.get("rule_id") or item.get("cve_id") or ""),
            rule_description=str(item.get("description") or item.get("title") or ""),
            state=str(item.get("state", "open")),
            created_at=_parse_dt(item.get("created_at")),
            html_url=str(item.get("github_url") or ""),
        )
        for item in recent
        if isinstance(item, dict)
    ]

    open_alerts = int(metrics_raw.get("open_alerts") or 0)
    return SecurityDashboard(
        metrics=SecurityMetrics(
            total_alerts=open_alerts,
            critical_count=int(metrics_raw.get("critical_count") or 0),
            high_count=int(metrics_raw.get("high_count") or 0),
            medium_count=int(metrics_raw.get("medium_count") or 0),
            low_count=int(metrics_raw.get("low_count") or 0),
            open_dependabot_prs=0,
            security_prs=0,
        ),
        recent_alerts=recent_alerts,
        recent_prs=[],
        sbom_available=False,
        data_source="control_plane",
    )


async def fetch_cp_security_payload() -> dict[str, Any] | None:
    """Load raw CP dashboard JSON when running in sandbox with telemetry credentials."""
    if not is_sandbox():
        return None

    base = get_cp_api_base()
    headers = get_cp_request_headers()
    if not base or not headers:
        return None

    url = f"{base}/api/internal/security/dashboard"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return None
            return data
    except Exception as exc:
        logger.warning("Control plane security dashboard unavailable: %s", exc)
        return None


async def fetch_cp_webhook_tenant_id() -> str | None:
    """Resolve tenant id (platform user id) for GitHub webhook path."""
    if not is_sandbox():
        return None
    base = get_cp_api_base()
    headers = get_cp_request_headers()
    if not base or not headers:
        return None
    url = f"{base}/api/internal/security/tenant"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            data = response.json()
            if isinstance(data, dict):
                raw = data.get("tenant_id")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    except Exception as exc:
        logger.warning("Control plane tenant resolve unavailable: %s", exc)
    return None


async def fetch_cp_security_dashboard() -> SecurityDashboard | None:
    """Mapped dashboard for backward-compatible imports."""
    payload = await fetch_cp_security_payload()
    if payload is None:
        return None
    return map_cp_dashboard(payload)
