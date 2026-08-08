"""Unit tests for POST /wiki/maintain mode param and compile-busy 409."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.maintain import WikiMaintainRunResult


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    return TestClient(build_minimal_app(preset="wiki"))


@pytest.fixture
def mock_archiver() -> MagicMock:
    archiver = MagicMock()
    archiver._llm = MagicMock()
    return archiver


def test_maintain_default_structural_mode(
    client: TestClient, mock_archiver: MagicMock
) -> None:
    from app.api.wiki.router import _get_wiki_archiver

    success = WikiMaintainRunResult(
        mode="structural",
        issues_found=1,
        issues_fixed=1,
        connections_discovered=0,
        duration_ms=5,
        open_actions_count=1,
        lint_issues=[
            {
                "issue_type": "broken_link",
                "severity": "medium",
                "location": "notes/alpha",
                "description": "Broken link to missing.md",
                "action_kind": "navigate",
                "suggested_fix": None,
            }
        ],
    )

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        with patch(
            "app.services.wiki.maintain.run_wiki_maintain_job",
            new=AsyncMock(return_value=success),
        ) as run_mock:
            response = client.post("/api/v1/wiki/maintain")

        assert response.status_code == 200
        data = response.json()
        assert data["open_actions_count"] == 1
        assert len(data["issues"]) == 1
        assert data["issues"][0]["action_kind"] == "navigate"
        run_mock.assert_awaited_once()
        assert run_mock.await_args.kwargs["mode"] == MaintainMode.STRUCTURAL
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)


def test_maintain_full_mode_query(client: TestClient, mock_archiver: MagicMock) -> None:
    from app.api.wiki.router import _get_wiki_archiver

    success = WikiMaintainRunResult(
        mode="full",
        issues_found=0,
        issues_fixed=0,
        connections_discovered=2,
        duration_ms=12,
    )

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        with patch(
            "app.services.wiki.maintain.run_wiki_maintain_job",
            new=AsyncMock(return_value=success),
        ) as run_mock:
            response = client.post("/api/v1/wiki/maintain?mode=full")

        assert response.status_code == 200
        assert run_mock.await_args.kwargs["mode"] == MaintainMode.FULL
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)


def test_maintain_compile_busy_returns_409(
    client: TestClient, mock_archiver: MagicMock
) -> None:
    from app.api.wiki.router import _get_wiki_archiver

    skipped = WikiMaintainRunResult(
        skipped=True,
        skipped_reason="compile_in_progress",
        mode="structural",
        summary_text="[SILENT]",
    )

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        with patch(
            "app.services.wiki.maintain.run_wiki_maintain_job",
            new=AsyncMock(return_value=skipped),
        ):
            response = client.post("/api/v1/wiki/maintain")

        assert response.status_code == 409
        assert "compilation is in progress" in response.json()["detail"].lower()
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)
