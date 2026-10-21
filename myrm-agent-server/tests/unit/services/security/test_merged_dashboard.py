"""Unit tests for merged security dashboard builder."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.security.dashboard import (
    DependabotPR,
    SecurityAlert,
    SecurityDashboard,
    SecurityMetrics,
)
from app.services.security.merged_dashboard import build_security_dashboard


def _cp_dashboard() -> SecurityDashboard:
    return SecurityDashboard(
        metrics=SecurityMetrics(
            total_alerts=2,
            critical_count=1,
            high_count=1,
            medium_count=0,
            low_count=0,
            open_dependabot_prs=0,
            security_prs=0,
        ),
        recent_alerts=[
            SecurityAlert(
                id=1,
                severity="high",
                rule_id="r1",
                rule_description="test",
                state="open",
                created_at=datetime.now(UTC),
                html_url="https://github.com/o/r/security/1",
            )
        ],
        recent_prs=[],
        sbom_available=False,
        data_source="control_plane",
    )


def _sample_pr() -> DependabotPR:
    return DependabotPR(
        number=99,
        title="Bump deps",
        state="open",
        labels=["security"],
        html_url="https://github.com/o/r/pull/99",
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_merge_includes_github_prs_when_cp_has_alerts() -> None:
    cp_payload = {
        "tenant_id": "user-42",
        "metrics": {"open_alerts": 2, "critical_count": 1, "high_count": 1},
        "recent_alerts": [{"id": 1, "severity": "high", "title": "x", "state": "open"}],
        "top_vulnerable_repos": [{"repo": "org/app", "alert_count": 2}],
    }
    pr_metrics = SecurityMetrics(
        total_alerts=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        open_dependabot_prs=1,
        security_prs=1,
    )

    with (
        patch(
            "app.services.security.merged_dashboard.fetch_cp_security_payload",
            AsyncMock(return_value=cp_payload),
        ),
        patch(
            "app.services.security.merged_dashboard._github_token",
            return_value="gh-test",
        ),
        patch(
            "app.services.security.merged_dashboard.fetch_github_supplement",
            AsyncMock(return_value=([_sample_pr()], pr_metrics, True)),
        ),
    ):
        result = await build_security_dashboard()

    assert result.data_source == "merged"
    assert len(result.recent_prs) == 1
    assert result.recent_prs[0].number == 99
    assert result.sbom_available is True
    assert result.metrics.open_dependabot_prs == 1


@pytest.mark.asyncio
async def test_sandbox_cp_empty_alerts_stays_control_plane_not_default_repo() -> None:
    cp_payload = {
        "tenant_id": "user-42",
        "metrics": {"open_alerts": 0, "critical_count": 0, "high_count": 0},
        "recent_alerts": [],
        "top_vulnerable_repos": [],
    }

    with (
        patch(
            "app.services.security.merged_dashboard.fetch_cp_security_payload",
            AsyncMock(return_value=cp_payload),
        ),
        patch(
            "app.services.security.merged_dashboard._github_token",
            return_value=None,
        ),
        patch(
            "app.services.security.merged_dashboard.build_github_dashboard",
            AsyncMock(),
        ) as mock_github,
    ):
        result = await build_security_dashboard()

    mock_github.assert_not_called()
    assert result.data_source == "control_plane"
    assert result.recent_alerts == []


@pytest.mark.asyncio
async def test_merge_stays_control_plane_when_github_supplement_empty() -> None:
    cp_payload = {
        "tenant_id": "user-42",
        "metrics": {"open_alerts": 1, "critical_count": 0, "high_count": 1},
        "recent_alerts": [{"id": 1, "severity": "high", "title": "x", "state": "open"}],
        "top_vulnerable_repos": [],
    }
    empty_pr_metrics = SecurityMetrics(
        total_alerts=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        open_dependabot_prs=0,
        security_prs=0,
    )

    with (
        patch(
            "app.services.security.merged_dashboard.fetch_cp_security_payload",
            AsyncMock(return_value=cp_payload),
        ),
        patch(
            "app.services.security.merged_dashboard._github_token",
            return_value="gh-test",
        ),
        patch(
            "app.services.security.merged_dashboard.load_monitored_github_repos",
            AsyncMock(return_value=["my-org/my-app"]),
        ),
        patch(
            "app.services.security.merged_dashboard.fetch_github_supplement",
            AsyncMock(return_value=([], empty_pr_metrics, False)),
        ),
    ):
        result = await build_security_dashboard()

    assert result.data_source == "control_plane"
    assert result.recent_prs == []
