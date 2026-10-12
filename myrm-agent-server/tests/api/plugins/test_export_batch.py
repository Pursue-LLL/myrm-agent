"""Batch / multi-expert export API tests (HTTP contract layer).

[INPUT]
- app.api.plugins.export::router (POS: export HTTP router mounted on test FastAPI app)
- tests.support.export_world::ExportWorld (POS: in-memory mock installation for skills/experts/servers)

[OUTPUT]
- Test cases for /export/batch/preview and /export/batch endpoints.

[POS]
Unit and contract tests for multi-expert batch packaging in Agent Plugins 1.0.0 format.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.plugins import export as export_module
from tests.support.export_world import SKILL_MD, ExportWorld


@pytest.fixture
def client() -> TestClient:
    app = FastAPI(title="Plugin Batch Export Test App")
    app.include_router(export_module.router, prefix="/api/v1/plugins")
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def world() -> Iterator[ExportWorld]:
    with ExportWorld().installed() as installation:
        yield installation


@pytest.fixture
def multi_team(world: ExportWorld) -> ExportWorld:
    """Setup two distinct standalone experts sharing a custom skill and having separate connectors."""
    world.custom_skill("local::shared_skill", "shared-notes", {"SKILL.md": SKILL_MD}, directory="shared-notes", source="clawhub")
    world.server(
        name="docs-api",
        type="streamable_http",
        url="https://docs.example.com/mcp",
        headers={"Authorization": "Bearer token"},
    )
    world.server(
        name="metrics-api",
        type="streamable_http",
        url="https://metrics.example.com/mcp",
        headers={"Authorization": "Bearer token2"},
    )
    world.expert(
        "agent-1",
        "Agent One",
        skills=("local::shared_skill",),
        mcps=("docs-api",),
        system_prompt="You are Agent One.",
    )
    world.expert(
        "agent-2",
        "Agent Two",
        skills=("local::shared_skill",),
        mcps=("metrics-api",),
        system_prompt="You are Agent Two.",
    )
    return world


def test_batch_export_preview_success(client: TestClient, multi_team: ExportWorld) -> None:
    res = client.post(
        "/api/v1/plugins/export/batch/preview",
        json={"agent_ids": ["agent-1", "agent-2"], "bundle_name": "team-bundle"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["plugin_name"] == "team-bundle"
    assert len(data["experts"]) == 2
    expert_names = {e["name"] for e in data["experts"]}
    assert expert_names == {"Agent One", "Agent Two"}
    for expert in data["experts"]:
        assert expert["is_entry"] is True

    # Custom skill should be deduplicated (only 1 skill card despite used by both)
    assert len(data["skills"]) == 1
    assert data["skills"][0]["name"] == "shared-notes"

    # Connectors from both agents are included
    connector_names = {c["name"] for c in data["connectors"]}
    assert connector_names == {"docs-api", "metrics-api"}


def test_batch_export_preview_not_found(client: TestClient, multi_team: ExportWorld) -> None:
    res = client.post(
        "/api/v1/plugins/export/batch/preview",
        json={"agent_ids": ["agent-1", "nonexistent-agent"]},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]["message"].lower()


def test_batch_export_preview_empty_rejected(client: TestClient, multi_team: ExportWorld) -> None:
    res = client.post(
        "/api/v1/plugins/export/batch/preview",
        json={"agent_ids": []},
    )
    assert res.status_code == 422


def test_batch_export_download_zip_success(client: TestClient, multi_team: ExportWorld) -> None:
    res = client.post(
        "/api/v1/plugins/export/batch",
        json={
            "agent_ids": ["agent-1", "agent-2"],
            "bundle_name": "team-bundle",
            "apply_redactions": True,
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert "team-bundle" in res.headers.get("content-disposition", "")

    # Inspect ZIP contents
    archive = zipfile.ZipFile(io.BytesIO(res.content))
    names = archive.namelist()
    assert any("plugin.json" in n for n in names)
    assert any("shared-notes" in n for n in names)
    # Check that both agents are included in the bundle
    assert any("Agent One" in n or "agent-one" in n for n in names)
    assert any("Agent Two" in n or "agent-two" in n for n in names)

    # Check that self-describing MIGRATION_CHECKLIST.md is generated
    checklist_path = next(n for n in names if "MIGRATION_CHECKLIST.md" in n)
    checklist_text = archive.read(checklist_path).decode("utf-8")
    assert "智能体全量资产迁移自省清单" in checklist_text
    assert "Agent One" in checklist_text
    assert "Agent Two" in checklist_text
    assert "shared-notes" in checklist_text
    assert "docs-api" in checklist_text
    assert "metrics-api" in checklist_text
