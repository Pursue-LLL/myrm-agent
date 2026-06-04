"""Unit tests for GitHub repo resolution on the security dashboard."""

from __future__ import annotations

from app.services.security.dashboard_settings import parse_monitored_repos_from_value
from app.services.security.github_supplement import resolve_github_repos


def test_parse_monitored_repos_normalizes_and_caps() -> None:
    raw = {
        "monitoredGithubRepos": [
            "  Org/App ",
            "org/app",
            "bad-slug",
            "other/repo",
            "four/extra",
        ]
    }
    assert parse_monitored_repos_from_value(raw) == ["Org/App", "other/repo", "four/extra"]


def test_resolve_github_repos_prefers_cp_then_user_config() -> None:
    payload = {
        "top_vulnerable_repos": [{"repo": "cp/org"}],
        "recent_alerts": [],
    }
    assert resolve_github_repos(
        payload,
        monitored_repos=["user/one", "user/two"],
        fallback_default=False,
    ) == ["cp/org"]


def test_resolve_github_repos_uses_monitored_when_cp_empty() -> None:
    payload: dict[str, object] = {"top_vulnerable_repos": [], "recent_alerts": []}
    assert resolve_github_repos(
        payload,
        monitored_repos=["my-org/app-a", "my-org/app-b"],
        fallback_default=False,
    ) == ["my-org/app-a", "my-org/app-b"]
