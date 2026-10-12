"""API endpoint tests for Managed Permission Template Presets, Session Checkpoint Rollback, and Connectors Hub."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.managed_permission_rollback_router import (
    router as managed_permission_rollback_router,
)
from app.services.security.managed_permission_rollback_service import (
    ManagedPermissionRollbackService,
    get_managed_permission_rollback_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ManagedPermissionRollbackService()
    app = FastAPI()
    app.include_router(managed_permission_rollback_router)
    app.dependency_overrides[get_managed_permission_rollback_service] = lambda: test_service
    return TestClient(app)


def test_templates_endpoints(client: TestClient) -> None:
    # 1. List templates
    resp = client.get("/managed-permissions/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) == 4
    roles = [t["role"] for t in templates]
    assert "AUDITOR" in roles
    assert "SAFE_COLLABORATOR" in roles

    # 2. Get specific template
    resp_auditor = client.get("/managed-permissions/templates/auditor")
    assert resp_auditor.status_code == 200
    assert resp_auditor.json()["role"] == "AUDITOR"
    assert resp_auditor.json()["allow_shell_execution"] is False

    # 3. Not found
    resp_404 = client.get("/managed-permissions/templates/unknown_role")
    assert resp_404.status_code == 404


def test_drift_check_endpoint(client: TestClient) -> None:
    # 1. Compliant
    resp_good = client.post(
        "/managed-permissions/templates/drift-check",
        json={
            "agent_id": "test_agent_good",
            "assigned_role": "AUDITOR",
            "active_rules": {
                "TOOLS": "DENY",
                "FILES": "ALWAYS_ALLOW",
                "APIS": "DENY",
                "SENDS": "DENY",
            },
            "active_allow_shell": False,
        },
    )
    assert resp_good.status_code == 200
    data_good = resp_good.json()
    assert data_good["is_compliant"] is True
    assert data_good["drift_score"] == 0.0

    # 2. Non-compliant drift
    resp_bad = client.post(
        "/managed-permissions/templates/drift-check",
        json={
            "agent_id": "test_agent_bad",
            "assigned_role": "AUDITOR",
            "active_rules": {
                "TOOLS": "ALWAYS_ALLOW",
                "FILES": "ALWAYS_ALLOW",
                "APIS": "ALWAYS_ALLOW",
                "SENDS": "ALWAYS_ALLOW",
            },
            "active_allow_shell": True,
        },
    )
    assert resp_bad.status_code == 200
    data_bad = resp_bad.json()
    assert data_bad["is_compliant"] is False
    assert len(data_bad["deviations"]) >= 4


def test_checkpoint_and_rollback_endpoints(client: TestClient) -> None:
    session_id = "session_api_test_42"

    # 1. Create checkpoint
    resp_create = client.post(
        "/managed-permissions/checkpoints/create",
        json={
            "session_id": session_id,
            "label": "Checkpoint Before Batch Edit",
            "files": {
                "index.html": "<h1>Hello</h1>",
                "app.js": "console.log('init');",
            },
            "memory_state": {"intent": "build frontend"},
            "active_role": "SAFE_COLLABORATOR",
        },
    )
    assert resp_create.status_code == 201
    ckpt_data = resp_create.json()
    checkpoint_id = ckpt_data["checkpoint_id"]
    assert ckpt_data["files_count"] == 2

    # 2. List checkpoints
    resp_list = client.get(f"/managed-permissions/checkpoints/{session_id}")
    assert resp_list.status_code == 200
    ckpts = resp_list.json()
    assert len(ckpts) == 1
    assert ckpts[0]["checkpoint_id"] == checkpoint_id

    # 3. Rollback checkpoint
    resp_rollback = client.post(
        "/managed-permissions/checkpoints/rollback",
        json={
            "checkpoint_id": checkpoint_id,
            "current_files": {
                "index.html": "<h1>Broken</h1>",
                "stale.tmp": "junk",
            },
        },
    )
    assert resp_rollback.status_code == 200
    rb_data = resp_rollback.json()
    assert rb_data["checkpoint_id"] == checkpoint_id
    assert rb_data["reverted_files_count"] >= 2
    assert rb_data["restored_files"]["index.html"] == "<h1>Hello</h1>"
    assert "stale.tmp" not in rb_data["restored_files"]


def test_connectors_hub_endpoints(client: TestClient) -> None:
    # 1. Register connector
    resp_reg = client.post(
        "/managed-permissions/connectors/register",
        json={
            "connector_id": "notion-workspace-sync",
            "channel_type": "NOTION",
            "display_name": "Company Wiki Sync",
            "account_identifier": "workspace_corp_99",
            "token_lifetime_seconds": 7200.0,
        },
    )
    assert resp_reg.status_code == 200
    conn = resp_reg.json()
    assert conn["connector_id"] == "notion-workspace-sync"
    assert conn["status"] == "ACTIVE"

    # 2. Record heartbeat
    resp_hb = client.post(
        "/managed-permissions/connectors/notion-workspace-sync/heartbeat"
    )
    assert resp_hb.status_code == 200
    assert resp_hb.json()["status"] == "ACTIVE"

    # 3. List connectors
    resp_list = client.get("/managed-permissions/connectors")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1
