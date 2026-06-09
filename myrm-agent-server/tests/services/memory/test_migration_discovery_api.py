"""Integration tests for migration discovery API endpoint.

Tests the GET /api/v1/migration/discover endpoint end-to-end with real filesystem
scanning (using tmp_path fixtures), verifying both local and SaaS mode behavior.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("memory", "migration_discovery")
@pytest.fixture()
def client() -> TestClient:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestDiscoveryEndpointLocalMode:
    """Discovery API in local/Tauri mode scans real filesystem."""

    @pytest.fixture(autouse=True)
    def _force_local_mode(self) -> None:
        with patch("app.api.migration.discovery.is_local_mode", return_value=True):
            yield  # type: ignore[misc]

    def test_discover_no_competitors(self, client: TestClient, tmp_path: Path) -> None:
        with patch(
            "app.api.migration.discovery.discover_competitors",
            wraps=__import__(
                "app.services.migration.competitor_discovery", fromlist=["discover_competitors"]
            ).discover_competitors,
        ) as mock_discover:
            mock_discover.side_effect = lambda home_dir=None: __import__(
                "app.services.migration.competitor_discovery", fromlist=["discover_competitors"]
            ).discover_competitors(str(tmp_path))

            resp = client.get("/api/v1/migration/discover")

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["sources"] == []

    def test_discover_with_hermes_data(self, client: TestClient, tmp_path: Path) -> None:
        hermes = tmp_path / ".hermes"
        hermes.mkdir()
        (hermes / "config.yaml").write_text("model: gpt-4o")
        mem = hermes / "memories"
        mem.mkdir()
        (mem / "MEMORY.md").write_text("- User likes Python\n- Uses VS Code")

        from app.services.migration.competitor_discovery import discover_competitors

        real_result = discover_competitors(str(tmp_path))

        with patch("app.api.migration.discovery.discover_competitors", return_value=real_result):
            resp = client.get("/api/v1/migration/discover")

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert len(data["sources"]) == 1
        src = data["sources"][0]
        assert src["competitor"] == "hermes"
        assert src["confidence"] == "high"
        assert src["memory_count_estimate"] == 2

    def test_discover_multiple_competitors(self, client: TestClient, tmp_path: Path) -> None:
        hermes = tmp_path / ".hermes"
        hermes.mkdir()
        (hermes / "config.yaml").write_text("m: 1")
        hm = hermes / "memories"
        hm.mkdir()
        (hm / "MEMORY.md").write_text("- fact")

        claude = tmp_path / ".claude"
        claude.mkdir()
        (claude / "CLAUDE.md").write_text("- pref")
        (claude / "settings.json").write_text("{}")

        from app.services.migration.competitor_discovery import discover_competitors

        real_result = discover_competitors(str(tmp_path))

        with patch("app.api.migration.discovery.discover_competitors", return_value=real_result):
            resp = client.get("/api/v1/migration/discover")

        data = resp.json()
        competitors = {s["competitor"] for s in data["sources"]}
        assert "hermes" in competitors
        assert "claude" in competitors

    def test_response_schema_fields(self, client: TestClient, tmp_path: Path) -> None:
        codex = tmp_path / ".codex"
        codex.mkdir()
        (codex / "instructions.md").write_text("# Instructions")
        (codex / "config.json").write_text("{}")

        from app.services.migration.competitor_discovery import discover_competitors

        real_result = discover_competitors(str(tmp_path))

        with patch("app.api.migration.discovery.discover_competitors", return_value=real_result):
            resp = client.get("/api/v1/migration/discover")

        data = resp.json()
        src = data["sources"][0]
        assert "competitor" in src
        assert "root" in src
        assert "confidence" in src
        assert "files" in src
        assert "memory_count_estimate" in src
        assert "skill_count" in src
        assert "has_api_keys" in src

        for f in src["files"]:
            assert "path" in f
            assert "kind" in f
            assert "size_bytes" in f


class TestDiscoveryEndpointSaaSMode:
    """Discovery API in SaaS mode returns empty with available=false."""

    @pytest.fixture(autouse=True)
    def _force_saas_mode(self) -> None:
        with patch("app.api.migration.discovery.is_local_mode", return_value=False):
            yield  # type: ignore[misc]

    def test_saas_mode_returns_unavailable(self, client: TestClient) -> None:
        resp = client.get("/api/v1/migration/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["sources"] == []
