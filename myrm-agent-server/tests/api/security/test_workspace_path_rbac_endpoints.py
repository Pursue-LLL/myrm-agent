"""API endpoint tests for Granular Workspace Path RBAC in myrm-agent-server."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.workspace_path_rbac import (
    GranularWorkspacePathGuard,
)

from app.api.security.workspace_path_rbac_router import (
    router as workspace_path_rbac_router,
)
from app.services.security.workspace_path_rbac_service import (
    WorkspacePathRbacService,
    get_workspace_path_rbac_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    guard = GranularWorkspacePathGuard()
    service = WorkspacePathRbacService(guard=guard)

    app.dependency_overrides[get_workspace_path_rbac_service] = lambda: service
    app.include_router(workspace_path_rbac_router, prefix="/api/v1/security")
    return TestClient(app)


def test_register_and_get_policy_api(client: TestClient) -> None:
    policy_payload = {
        "policy": {
            "policy_id": "pol_api_01",
            "user_identity": "alice@corp.com",
            "project_root": "/workspace/demo",
            "rules": [
                {"pattern": "raw_data/*", "mode": "ro", "description": "Raw data"},
                {"pattern": "deliverables/*", "mode": "rw", "description": "Output"},
            ],
            "allowed_deliverables_dir": "deliverables",
        }
    }
    # 1. Register policy
    resp = client.post(
        "/api/v1/security/workspace-path-rbac/policies", json=policy_payload
    )
    assert resp.status_code == 201
    assert resp.json()["policy_id"] == "pol_api_01"

    # 2. Get policy
    get_resp = client.get("/api/v1/security/workspace-path-rbac/policies/pol_api_01")
    assert get_resp.status_code == 200
    assert get_resp.json()["user_identity"] == "alice@corp.com"

    # 3. Nonexistent policy
    missing_resp = client.get(
        "/api/v1/security/workspace-path-rbac/policies/nonexistent_pol"
    )
    assert missing_resp.status_code == 404


def test_check_access_and_write_denial_api(client: TestClient) -> None:
    # Setup policy
    client.post(
        "/api/v1/security/workspace-path-rbac/policies",
        json={
            "policy": {
                "policy_id": "pol_gate_api",
                "user_identity": "bob@corp.com",
                "project_root": "/workspace",
                "rules": [
                    {"pattern": "inputs/*", "mode": "ro"},
                    {"pattern": "deliverables/*", "mode": "rw"},
                ],
                "allowed_deliverables_dir": "deliverables",
            }
        },
    )

    # 1. Permitted Read
    read_payload = {
        "policy_id": "pol_gate_api",
        "agent_id": "agent_alpha",
        "session_id": "sess_api_01",
        "user_identity": "bob@corp.com",
        "relative_path": "inputs/data.csv",
        "action": "READ",
    }
    resp_read = client.post(
        "/api/v1/security/workspace-path-rbac/check", json=read_payload
    )
    assert resp_read.status_code == 200
    assert resp_read.json()["allowed"] is True

    # 2. Blocked Direct Write
    write_payload = {
        "policy_id": "pol_gate_api",
        "agent_id": "agent_alpha",
        "session_id": "sess_api_01",
        "user_identity": "bob@corp.com",
        "relative_path": "inputs/data.csv",
        "action": "DIRECT_WRITE",
    }
    resp_write = client.post(
        "/api/v1/security/workspace-path-rbac/check", json=write_payload
    )
    assert resp_write.status_code == 200
    data_write = resp_write.json()
    assert data_write["allowed"] is False
    assert data_write["violation_reason"] == "READ_ONLY_PATH"
    assert "deliverables/data.csv" in data_write["auto_reroute_hint"]
    assert data_write["denial_card"]["blocked_path"] == "inputs/data.csv"


def test_audit_ledger_and_stats_api(client: TestClient) -> None:
    client.post(
        "/api/v1/security/workspace-path-rbac/policies",
        json={
            "policy": {
                "policy_id": "pol_audit_api",
                "user_identity": "carol@corp.com",
                "project_root": "/workspace",
                "rules": [{"pattern": "raw/*", "mode": "ro"}],
                "allowed_deliverables_dir": "deliverables",
            }
        },
    )

    # Trigger operations
    client.post(
        "/api/v1/security/workspace-path-rbac/check",
        json={
            "policy_id": "pol_audit_api",
            "agent_id": "agent_carol",
            "session_id": "sess_audit_api",
            "user_identity": "carol@corp.com",
            "relative_path": "raw/doc.txt",
            "action": "READ",
        },
    )
    client.post(
        "/api/v1/security/workspace-path-rbac/check",
        json={
            "policy_id": "pol_audit_api",
            "agent_id": "agent_carol",
            "session_id": "sess_audit_api",
            "user_identity": "carol@corp.com",
            "relative_path": "raw/doc.txt",
            "action": "COPY_WRITE",
        },
    )

    # 1. Query audit ledger
    ledger_resp = client.get(
        "/api/v1/security/workspace-path-rbac/audit-ledger?session_id=sess_audit_api"
    )
    assert ledger_resp.status_code == 200
    records = ledger_resp.json()
    assert len(records) == 2

    # 2. Query stats
    stats_resp = client.get("/api/v1/security/workspace-path-rbac/audit-stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_events"] >= 2
    assert stats["granted_count"] >= 1
    assert stats["denied_count"] >= 1
