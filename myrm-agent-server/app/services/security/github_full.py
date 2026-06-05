"""Full security dashboard sourced from GitHub APIs (local / fallback)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.api.security.dashboard_models import SecurityAlert, SecurityDashboard, SecurityMetrics
from app.services.security.github_supplement import (
    fetch_github_supplement,
)


def _parse_github_obj(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _github_rule(alert: dict[str, object]) -> dict[str, object]:
    return _parse_github_obj(alert.get("rule"))


def _github_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default


def _github_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    return datetime.fromtimestamp(0, tz=UTC)


async def _fetch_github_list(endpoint: str, token: str | None) -> list[dict[str, object]]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com{endpoint}",
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, list):
        return []
    return [{str(k): v for k, v in item.items()} for item in body if isinstance(item, dict)]


async def build_github_dashboard(
    repo: str,
    token: str | None,
    *,
    supplement_repos: list[str] | None = None,
) -> SecurityDashboard:
    alerts_data = await _fetch_github_list(f"/repos/{repo}/code-scanning/alerts", token)

    critical_count = sum(
        1
        for alert in alerts_data
        if _github_rule(alert).get("security_severity_level") == "critical" and alert.get("state") == "open"
    )
    high_count = sum(
        1
        for alert in alerts_data
        if _github_rule(alert).get("security_severity_level") == "high" and alert.get("state") == "open"
    )
    medium_count = sum(
        1
        for alert in alerts_data
        if _github_rule(alert).get("security_severity_level") == "medium" and alert.get("state") == "open"
    )
    low_count = sum(
        1 for alert in alerts_data if _github_rule(alert).get("security_severity_level") == "low" and alert.get("state") == "open"
    )

    recent_alerts = [
        SecurityAlert(
            id=_github_int(alert.get("number")),
            severity=str(_github_rule(alert).get("security_severity_level", "unknown")),
            rule_id=str(_github_rule(alert).get("id", "")),
            rule_description=str(_github_rule(alert).get("description", "")),
            state=str(alert.get("state", "")),
            created_at=_github_datetime(alert.get("created_at")),
            html_url=str(alert.get("html_url", "")),
        )
        for alert in alerts_data[:10]
    ]

    pr_repos = supplement_repos if supplement_repos else [repo]
    recent_prs, pr_metrics, sbom_available = await fetch_github_supplement(pr_repos, token)

    return SecurityDashboard(
        metrics=SecurityMetrics(
            total_alerts=len(alerts_data),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            open_dependabot_prs=pr_metrics.open_dependabot_prs,
            security_prs=pr_metrics.security_prs,
        ),
        recent_alerts=recent_alerts,
        recent_prs=recent_prs,
        sbom_available=sbom_available,
        data_source="github",
    )
