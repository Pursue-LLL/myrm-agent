"""Integration tests for migration discovery API endpoint.

Tests the GET /api/v1/migration/discover endpoint end-to-end with real filesystem
scanning (using tmp_path fixtures), verifying both local and SaaS mode behavior.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.migration.discovery import MigrationSourceManifestItemResponse, _to_response
from app.services.migration.source.source_discovery import DiscoveryResult, ExternalSource
from app.services.migration.source.source_secrets_importer import SecretsImportResult, SkippedKey
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("memory", "migration_discovery")


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestDiscoveryEndpointLocalMode:
    """Discovery API in local/Tauri mode scans real filesystem."""

    @pytest.fixture(autouse=True)
    def _force_local_mode(self) -> Iterator[None]:
        with patch("app.api.migration.discovery.is_local_mode", return_value=True):
            yield

    def test_discover_no_competitors(self, client: TestClient, tmp_path: Path) -> None:
        with patch(
            "app.api.migration.discovery.discover_external_sources",
            wraps=__import__(
                "app.services.migration.source.source_discovery",
                fromlist=["discover_external_sources"],
            ).discover_external_sources,
        ) as mock_discover:
            mock_discover.side_effect = lambda home_dir=None: __import__(
                "app.services.migration.source.source_discovery",
                fromlist=["discover_external_sources"],
            ).discover_external_sources(str(tmp_path))

            resp = client.get("/api/v1/migration/discover")

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["sources"] == []
        assert isinstance(data["source_manifest"], list)
        assert data["source_manifest_authoritative"] is True
        assert {item["id"] for item in data["source_manifest"]} == {
            "hermes",
            "openclaw",
            "claude",
            "codex",
            "chatgpt",
            "gbrain",
            "pi",
            "plur",
        }

    def test_discover_with_hermes_data(self, client: TestClient, tmp_path: Path) -> None:
        hermes = tmp_path / ".hermes"
        hermes.mkdir()
        (hermes / "config.yaml").write_text("model: gpt-4o")
        mem = hermes / "memories"
        mem.mkdir()
        (mem / "MEMORY.md").write_text("- User likes Python\n- Uses VS Code")

        from app.services.migration.source.source_discovery import (
            discover_external_sources,
        )

        real_result = discover_external_sources(str(tmp_path))

        with patch(
            "app.api.migration.discovery.discover_external_sources",
            return_value=real_result,
        ):
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

        from app.services.migration.source.source_discovery import (
            discover_external_sources,
        )

        real_result = discover_external_sources(str(tmp_path))

        with patch(
            "app.api.migration.discovery.discover_external_sources",
            return_value=real_result,
        ):
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

        from app.services.migration.source.source_discovery import (
            discover_external_sources,
        )

        real_result = discover_external_sources(str(tmp_path))

        with patch(
            "app.api.migration.discovery.discover_external_sources",
            return_value=real_result,
        ):
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
        assert "can_import_secrets" in src
        assert "source_manifest" in data
        assert isinstance(data["source_manifest"], list)
        assert data["source_manifest_authoritative"] is True
        manifest_item = data["source_manifest"][0]
        assert "id" in manifest_item
        assert "display_name" in manifest_item
        assert "import_source" in manifest_item
        assert "discover_modes" in manifest_item
        assert "deep_link_enabled" in manifest_item

        for f in src["files"]:
            assert "path" in f
            assert "kind" in f
            assert "size_bytes" in f

    def test_discover_downgrades_authoritative_when_manifest_incomplete(self, client: TestClient) -> None:
        partial_manifest = [
            MigrationSourceManifestItemResponse(
                id="hermes",
                display_name="Hermes",
                import_source="hermes",
                discover_modes=["local_scan"],
                deep_link_enabled=True,
            )
        ]
        with (
            patch(
                "app.api.migration.discovery.build_source_manifest_response",
                return_value=partial_manifest,
            ),
            patch(
                "app.api.migration.discovery.discover_external_sources",
                return_value=DiscoveryResult(sources=[], scan_path="/tmp"),
            ),
        ):
            resp = client.get("/api/v1/migration/discover")

        assert resp.status_code == 200
        data = resp.json()
        assert data["source_manifest_authoritative"] is False
        assert [item["id"] for item in data["source_manifest"]] == ["hermes"]


class TestDiscoveryEndpointSaaSMode:
    """Discovery API in SaaS mode returns empty with available=false."""

    @pytest.fixture(autouse=True)
    def _force_saas_mode(self) -> Iterator[None]:
        with patch("app.api.migration.discovery.is_local_mode", return_value=False):
            yield

    def test_saas_mode_returns_unavailable(self, client: TestClient) -> None:
        resp = client.get("/api/v1/migration/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["sources"] == []
        assert isinstance(data["source_manifest"], list)
        assert data["source_manifest_authoritative"] is True

    def test_saas_mode_refuses_the_key_import(self, client: TestClient) -> None:
        resp = client.post("/api/v1/migration/secrets/import", json={"root": "/tmp/hermes", "competitor": "hermes"})

        assert resp.status_code == 403


class TestKeyImportOffer:
    """A source offers the opt-in key import only for keys the import reads, and only where it can run."""

    @pytest.mark.parametrize(
        ("local_mode", "has_importable_keys", "offered"),
        [(True, True, True), (True, False, False), (False, True, False)],
    )
    def test_can_import_secrets(self, local_mode: bool, has_importable_keys: bool, offered: bool) -> None:
        source = ExternalSource(
            competitor="hermes", root="/tmp/hermes", has_api_keys=True, has_importable_keys=has_importable_keys
        )

        with patch("app.api.migration.discovery.is_local_mode", return_value=local_mode):
            response = _to_response(source)

        assert response.has_api_keys is True
        assert response.can_import_secrets is offered


class TestSecretsImportEndpoint:
    """POST /migration/secrets/import reports what it imported and what it left alone, by name."""

    @pytest.fixture(autouse=True)
    def _force_local_mode(self) -> Iterator[None]:
        with patch("app.api.migration.discovery.is_local_mode", return_value=True):
            yield

    def test_the_response_names_imported_keys_and_the_reason_for_each_key_left_alone(self, client: TestClient) -> None:
        result = SecretsImportResult(
            imported_keys=["OPENAI_API_KEY"],
            skipped_keys=[SkippedKey("GLM_API_KEY", "needs_endpoint"), SkippedKey("TAVILY_API_KEY", "unsupported")],
        )

        with patch("app.api.migration.discovery.import_external_source_secrets", return_value=result):
            resp = client.post("/api/v1/migration/secrets/import", json={"root": "/tmp/hermes", "competitor": "hermes"})

        assert resp.status_code == 200
        assert resp.json() == {
            "imported_keys": ["OPENAI_API_KEY"],
            "skipped_keys": [
                {"name": "GLM_API_KEY", "reason": "needs_endpoint"},
                {"name": "TAVILY_API_KEY", "reason": "unsupported"},
            ],
        }

    def test_an_import_that_cannot_run_is_a_client_error(self, client: TestClient) -> None:
        with patch(
            "app.api.migration.discovery.import_external_source_secrets",
            side_effect=ValueError("Providers config is not an object"),
        ):
            resp = client.post("/api/v1/migration/secrets/import", json={"root": "/tmp/hermes", "competitor": "hermes"})

        assert resp.status_code == 400
        assert "Providers config is not an object" in resp.text
