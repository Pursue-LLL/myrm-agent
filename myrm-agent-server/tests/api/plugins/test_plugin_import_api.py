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
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.plugins.models import PluginParseResult

from app.api.plugins import import_ as import_module
from app.services.plugins.import_service import PluginImportSession

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

_FAKE_DB_PATH = Path("/tmp/plugin-import-test/skills.db")


@pytest.fixture(scope="function")
def client() -> TestClient:
    test_app = FastAPI(title="Plugin Import Test App")
    test_app.include_router(import_module.router, prefix="/api/v1/plugins")
    return TestClient(test_app)


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


def test_confirm_persists_components(client: TestClient, tmp_path: Path) -> None:
    session_id = "sess-api-1"

    fake_store = AsyncMock()
    config_service = AsyncMock()
    agent_service = AsyncMock()

    with (
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
