"""Agent Plugins import API endpoint tests (HTTP contract layer).

Covers /import/preview (upload, limits, security issues, diagnostics) and
/import/confirm (session load, persistence, stale-session errors) using an
isolated FastAPI app with the plugin import router mounted.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.plugins.models import PluginParseResult

from app.api.plugins import import_ as import_module
from app.services.plugins.import_service import PluginImportSession

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


@pytest.fixture(scope="function")
def client() -> TestClient:
    test_app = FastAPI(title="Plugin Import Test App")
    test_app.include_router(import_module.router, prefix="/api/v1/plugins")
    # Map uncaught exceptions to 500 responses so tests assert HTTP behavior
    # rather than exception propagation through the test client.
    return TestClient(test_app, raise_server_exceptions=False)


def _plugin_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "demo-plugin/plugin.json",
            json.dumps(
                {
                    "$schema": PLUGIN_SCHEMA,
                    "name": "demo-plugin",
                    "version": "1.0.0",
                    "description": "Demo",
                    "author": {"name": "Acme"},
                }
            ),
        )
        zf.writestr(
            "demo-plugin/skills/summarize/SKILL.md",
            "---\nname: summarize\ndescription: Do summaries\n---\nWork.",
        )
        zf.writestr(
            "demo-plugin/mcp.json",
            json.dumps(
                {
                    "$schema": MCP_SCHEMA,
                    "mcpServers": {
                        "pdf-server": {"type": "stdio", "command": "./bin/pdf"},
                    },
                }
            ),
        )
    return buf.getvalue()


def test_preview_returns_component_preview(client: TestClient, tmp_path: Path) -> None:
    with (
        patch(
            "app.services.plugins.import_service._load_existing_skill_ids",
            return_value={},
        ),
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service._scan_skill_security",
            return_value=[],
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/preview",
            files={
                "file": ("demo-plugin.zip", _plugin_zip_bytes(), "application/zip")
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["plugin"]["name"] == "demo-plugin"
    assert body["is_valid"] is True
    assert len(body["skills"]) == 1
    assert body["skills"][0]["name"] == "summarize"
    assert body["skills"][0]["security_issues"] == []
    assert len(body["servers"]) == 1
    assert body["servers"][0]["name"] == "pdf-server"


def test_preview_rejects_non_zip(client: TestClient) -> None:
    response = client.post(
        "/api/v1/plugins/import/preview",
        files={"file": ("plugin.txt", b"not a zip", "text/plain")},
    )
    assert response.status_code == 400


def test_preview_rejects_corrupt_zip_bytes(client: TestClient) -> None:
    """A .zip-named upload with garbage bytes must be a 400, not a 500.

    ``zipfile.BadZipFile`` (raised by safe_extract_zip on non-zip content)
    is not a ``ValueError`` subclass, so the endpoint relies on
    ``parse_plugin_zip`` mapping it to a user-facing 400.
    """
    response = client.post(
        "/api/v1/plugins/import/preview",
        files={"file": ("plugin.zip", b"\x00\x01not a real zip", "application/zip")},
    )
    assert response.status_code == 400


def test_preview_rejects_empty_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/plugins/import/preview",
        files={"file": ("plugin.zip", b"", "application/zip")},
    )
    assert response.status_code == 400


def test_preview_rejects_oversized_zip(client: TestClient) -> None:
    oversize = b"x" * (import_module.MAX_PLUGIN_ZIP_BYTES + 1)
    response = client.post(
        "/api/v1/plugins/import/preview",
        files={"file": ("plugin.zip", oversize, "application/zip")},
    )
    assert response.status_code == 400


def test_preview_security_error_returns_structured_detail(
    client: TestClient, tmp_path: Path
) -> None:
    """Archive security violations map to a 400 with a structured detail.

    The ``{message, error_code}`` detail is the contract the frontend uses to
    localize archive-security errors (``resolveUserFacingArchiveSecurityError``).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Highly compressible entry drives the compression ratio above the
        # 100:1 zip-bomb threshold.
        zf.writestr("bomb-plugin/plugin.json", "x" * 5_000_000)
    response = client.post(
        "/api/v1/plugins/import/preview",
        files={"file": ("bomb.zip", buf.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "archive_security.compression_ratio_exceeded"
    assert detail["message"]


def test_preview_returns_500_when_session_persist_fails(
    client: TestClient, tmp_path: Path
) -> None:
    with (
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service._scan_skill_security",
            return_value=[],
        ),
        patch(
            "app.services.plugins.import_service.PluginStaging.save_session",
            side_effect=RuntimeError("disk full"),
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/preview",
            files={
                "file": ("demo-plugin.zip", _plugin_zip_bytes(), "application/zip")
            },
        )

    assert response.status_code == 500


def test_preview_flags_dangerous_skill(
    client: TestClient, tmp_path: Path
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "danger-plugin/plugin.json",
            json.dumps(
                {
                    "$schema": PLUGIN_SCHEMA,
                    "name": "danger-plugin",
                    "version": "1.0.0",
                    "description": "Dangerous",
                }
            ),
        )
        zf.writestr(
            "danger-plugin/skills/wipe/SKILL.md",
            "---\nname: wipe\ndescription: Wipes stuff\n---\nRun `rm -rf /`.",
        )
    with (
        patch(
            "app.services.plugins.import_service._load_existing_skill_ids",
            return_value={},
        ),
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service._scan_skill_security",
            return_value=["Dangerous pattern detected"],
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/preview",
            files={"file": ("danger.zip", buf.getvalue(), "application/zip")},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["skills"]) == 1
    assert body["skills"][0]["security_issues"] == ["Dangerous pattern detected"]
    # The flag must survive the response-model serialization (extra="ignore" would
    # silently drop it, breaking the frontend's oversized-skill hint).
    assert body["skills"][0]["oversized_content"] is False


def test_preview_surfaces_oversized_skill_flag(
    client: TestClient, tmp_path: Path
) -> None:
    """oversized_content must reach the HTTP contract, not vanish in the model."""
    from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(
            "huge-plugin/plugin.json",
            json.dumps(
                {
                    "$schema": PLUGIN_SCHEMA,
                    "name": "huge-plugin",
                    "version": "1.0.0",
                    "description": "Huge skill",
                }
            ),
        )
        zf.writestr(
            "huge-plugin/skills/huge/SKILL.md",
            "---\nname: huge\ndescription: Too big\n---\n"
            + "x" * (SkillStore.MAX_SKILL_CONTENT_CHARS + 1024),
        )
    with (
        patch(
            "app.services.plugins.import_service._load_existing_skill_ids",
            return_value={},
        ),
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service._scan_skill_security",
            return_value=[],
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/preview",
            files={"file": ("huge.zip", buf.getvalue(), "application/zip")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["skills"][0]["oversized_content"] is True


def test_preview_surfaces_name_conflict_flag(
    client: TestClient, tmp_path: Path
) -> None:
    """conflict must reach the HTTP contract, not vanish in the response model."""
    with (
        patch(
            "app.services.plugins.import_service._load_existing_skill_ids",
            return_value={"summarize": "existing-skill-id"},
        ),
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service._scan_skill_security",
            return_value=[],
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/preview",
            files={
                "file": ("demo-plugin.zip", _plugin_zip_bytes(), "application/zip")
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["skills"][0]["conflict"] is True


def test_confirm_persists_components(client: TestClient, tmp_path: Path) -> None:
    session_id = "sess-api-1"

    fake_store = AsyncMock()
    fake_store.get_active_skills = lambda: []
    config_service = AsyncMock()
    agent_service = AsyncMock()

    with (
        patch(
            "app.services.plugins.import_service._load_existing_skill_ids",
            return_value={},
        ),
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.core.skills.store.evolution_store.get_evolution_skill_store",
            return_value=fake_store,
        ),
        patch(
            "app.services.config.service.config_service",
            config_service,
        ),
        patch(
            "app.services.agent.agent_service.AgentService",
            agent_service,
        ),
        patch(
            "app.services.plugins.import_service.PluginStaging.load_session",
            return_value=PluginImportSession(
                plugin_result=PluginParseResult(),
                skills_by_key={},
                servers_by_key={},
            ),
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/confirm",
            json={
                "session_id": session_id,
                "skills": [],
                "servers": [],
                "bind_agent_id": None,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_skills"] == 0
    assert body["imported_servers"] == 0


def test_confirm_rejects_stale_session(client: TestClient, tmp_path: Path) -> None:
    with (
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service.PluginStaging.load_session",
            side_effect=FileNotFoundError("missing"),
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/confirm",
            json={
                "session_id": "missing-session",
                "skills": [],
                "servers": [],
                "bind_agent_id": None,
            },
        )

    assert response.status_code == 400


def test_confirm_returns_500_on_service_failure(
    client: TestClient, tmp_path: Path
) -> None:
    with (
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service.PluginStaging.load_session",
            return_value=PluginImportSession(
                plugin_result=PluginParseResult(),
                skills_by_key={},
                servers_by_key={},
            ),
        ),
        patch(
            "app.services.plugins.import_service.confirm_plugin_import",
            side_effect=RuntimeError("db down"),
        ),
    ):
        response = client.post(
            "/api/v1/plugins/import/confirm",
            json={
                "session_id": "boom",
                "skills": [],
                "servers": [],
                "bind_agent_id": None,
            },
        )

    assert response.status_code == 500


def test_preview_confirm_roundtrip(client: TestClient, tmp_path: Path) -> None:
    """Real preview → real confirm roundtrip against a tmp staging dir.

    No ``load_session`` mock: the session file written by /preview is
    read back by /confirm, then removed by ``cleanup_session``.
    """
    with (
        patch(
            "app.api.plugins.import_.get_evolution_skill_store_db_path",
            return_value=tmp_path / "skills.db",
        ),
        patch(
            "app.services.plugins.import_service._scan_skill_security",
            return_value=[],
        ),
        patch(
            "app.core.skills.store.evolution_store.get_evolution_skill_store",
            return_value=SimpleNamespace(
                save_skills_batch=AsyncMock(),
                get_active_skills=lambda: [],
            ),
        ),
        patch(
            "app.services.config.service.config_service",
            AsyncMock(),
        ),
        patch(
            "app.services.agent.agent_service.AgentService",
            AsyncMock(),
        ),
    ):
        preview_response = client.post(
            "/api/v1/plugins/import/preview",
            files={
                "file": ("demo-plugin.zip", _plugin_zip_bytes(), "application/zip")
            },
        )

        assert preview_response.status_code == 200
        session_id = preview_response.json()["session_id"]
        staging_file = tmp_path / "plugin_staging" / f"{session_id}.pkl"
        assert staging_file.exists()

        confirm_response = client.post(
            "/api/v1/plugins/import/confirm",
            json={
                "session_id": session_id,
                "skills": [],
                "servers": [],
                "bind_agent_id": None,
            },
        )

    assert confirm_response.status_code == 200
    body = confirm_response.json()
    assert body["imported_skills"] == 0
    assert body["imported_servers"] == 0
    assert not staging_file.exists(), "confirm must clean up its session file"


def test_list_installed_plugins(client: TestClient) -> None:
    """GET /installed proxies the service layer's provenance-grouped listing."""
    with (
        patch(
            "app.api.plugins.import_.list_installed_plugins",
            new=AsyncMock(
                return_value=[
                    {"name": "demo-plugin", "servers": ["pdf-server"], "has_bundled_files": True},
                    {"name": "other-plugin", "servers": ["srv-a", "srv-b"], "has_bundled_files": False},
                ]
            ),
        ),
    ):
        response = client.get("/api/v1/plugins/import/installed")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {"name": "demo-plugin", "servers": ["pdf-server"], "has_bundled_files": True},
        {"name": "other-plugin", "servers": ["srv-a", "srv-b"], "has_bundled_files": False},
    ]


def test_uninstall_plugin(client: TestClient) -> None:
    """DELETE /{plugin_name} proxies the service layer's uninstall result."""
    with (
        patch(
            "app.api.plugins.import_.uninstall_plugin",
            new=AsyncMock(
                return_value={
                    "plugin_name": "demo-plugin",
                    "removed_servers": 2,
                    "unbound_agents": 1,
                    "removed_files": True,
                }
            ),
        ),
    ):
        response = client.delete("/api/v1/plugins/import/demo-plugin")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "plugin_name": "demo-plugin",
        "removed_servers": 2,
        "unbound_agents": 1,
        "removed_files": True,
    }
