"""Workspace trust REST API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.security.workspace_trust.types import (
    WorkspaceTrustEntry,
    WorkspaceTrustLevel,
    WorkspaceTrustManifest,
)

from app.api.security import workspace_trust as workspace_trust_module


@pytest.fixture(scope="function")
def client() -> TestClient:
    test_app = FastAPI(title="Workspace Trust Test App")
    test_app.include_router(workspace_trust_module.router, prefix="/api/v1/security/workspace-trust")
    return TestClient(test_app, raise_server_exceptions=False)


def _sample_manifest() -> WorkspaceTrustManifest:
    return WorkspaceTrustManifest(
        path="/tmp/demo",
        canonical_path="/tmp/demo",
        skill_count=2,
        rule_count=1,
        repo_command_prefixes=("npm run test",),
        has_myrm_config=True,
        current_level=None,
    )


def test_manifest_preview(client: TestClient) -> None:
    manifest = _sample_manifest()
    mock_store = AsyncMock()
    mock_store.loaded = True
    mock_store.load = AsyncMock()
    mock_store.build_manifest = AsyncMock(return_value=manifest)

    with patch(
        "app.api.security.workspace_trust.get_workspace_trust_store",
        return_value=mock_store,
    ):
        response = client.post("/api/v1/security/workspace-trust/manifest", json={"path": "/tmp/demo"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["skill_count"] == 2
    assert body["data"]["rule_count"] == 1


def test_decide_trust_persists(client: TestClient) -> None:
    manifest = _sample_manifest()
    entry = WorkspaceTrustEntry(
        path="/tmp/demo",
        level=WorkspaceTrustLevel.TRUSTED,
        decided_at="2026-08-31T00:00:00+00:00",
        manifest_hash="abc123",
    )
    mock_store = AsyncMock()
    mock_store.loaded = True
    mock_store.load = AsyncMock()
    mock_store.build_manifest = AsyncMock(return_value=manifest)
    mock_store.decide = AsyncMock(return_value=entry)

    with patch(
        "app.api.security.workspace_trust.get_workspace_trust_store",
        return_value=mock_store,
    ):
        response = client.post(
            "/api/v1/security/workspace-trust/decide",
            json={"path": "/tmp/demo", "level": "TRUSTED"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["level"] == "TRUSTED"
    mock_store.decide.assert_awaited_once()


def test_list_trusted_folders(client: TestClient) -> None:
    entry = WorkspaceTrustEntry(
        path="/tmp/demo",
        level=WorkspaceTrustLevel.TRUSTED,
        decided_at="2026-08-31T00:00:00+00:00",
        manifest_hash="",
    )
    mock_store = AsyncMock()
    mock_store.loaded = True
    mock_store.load = AsyncMock()
    mock_store.list_entries = lambda: [entry]

    with patch(
        "app.api.security.workspace_trust.get_workspace_trust_store",
        return_value=mock_store,
    ):
        response = client.get("/api/v1/security/workspace-trust")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
