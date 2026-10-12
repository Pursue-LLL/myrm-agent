"""Integration tests for Policy Snapshot API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.policy_snapshot_router import router as policy_snapshot_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting policy_snapshot_router."""
    test_app = FastAPI(title="Policy Snapshot Test App")
    test_app.include_router(policy_snapshot_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_active_and_bind_endpoints(client: TestClient) -> None:
    # 1. Get active snapshot
    resp = client.get("/api/v1/security/policy-snapshot/active")
    assert resp.status_code == 200
    active = resp.json()
    assert active["version_number"] >= 1
    assert "read_file" in active["allowed_tools"]

    # 2. Bind task
    bind_resp = client.post(
        "/api/v1/security/policy-snapshot/bind",
        json={"task_id": "task_api_001"},
    )
    assert bind_resp.status_code == 201
    assert bind_resp.json()["version_number"] == active["version_number"]

    # 3. Get task pinned policy
    task_resp = client.get("/api/v1/security/policy-snapshot/tasks/task_api_001")
    assert task_resp.status_code == 200
    assert task_resp.json()["snapshot_id"] == bind_resp.json()["snapshot_id"]


def test_soft_update_dual_track_endpoint(client: TestClient) -> None:
    # 1. Bind in-flight task
    client.post(
        "/api/v1/security/policy-snapshot/bind",
        json={"task_id": "task_in_flight"},
    )

    # 2. Track A Soft Update
    update_payload = {
        "prompt_template": "System Prompt New Generation",
        "allowed_tools": ["read_file", "search_web", "exclusive_new_tool"],
        "governance_rules": {"max_iterations": 50},
    }
    update_resp = client.post("/api/v1/security/policy-snapshot/soft-update", json=update_payload)
    assert update_resp.status_code == 200
    v2_snapshot = update_resp.json()
    assert "exclusive_new_tool" in v2_snapshot["allowed_tools"]

    # 3. Assert tool on in-flight task: exclusive_new_tool must be blocked!
    assert_resp1 = client.post(
        "/api/v1/security/policy-snapshot/assert-tool",
        json={"task_id": "task_in_flight", "tool_name": "exclusive_new_tool"},
    )
    assert assert_resp1.status_code == 200
    assert assert_resp1.json()["allowed"] is False

    # 4. Bind new task: exclusive_new_tool allowed
    client.post(
        "/api/v1/security/policy-snapshot/bind",
        json={"task_id": "task_subsequent"},
    )
    assert_resp2 = client.post(
        "/api/v1/security/policy-snapshot/assert-tool",
        json={"task_id": "task_subsequent", "tool_name": "exclusive_new_tool"},
    )
    assert assert_resp2.status_code == 200
    assert assert_resp2.json()["allowed"] is True


def test_emergency_hot_kill_and_revoke_endpoint(client: TestClient) -> None:
    client.post(
        "/api/v1/security/policy-snapshot/bind",
        json={"task_id": "task_hotkill_test"},
    )

    # Verify read_file is initially allowed
    c1 = client.post(
        "/api/v1/security/policy-snapshot/assert-tool",
        json={"task_id": "task_hotkill_test", "tool_name": "read_file"},
    )
    assert c1.json()["allowed"] is True

    # Track B: Emergency Hot Kill
    hk_resp = client.post(
        "/api/v1/security/policy-snapshot/emergency-hot-kill",
        json={"revoked_tools": ["read_file"], "reason": "Severe leak incident"},
    )
    assert hk_resp.status_code == 201
    directive_id = hk_resp.json()["directive_id"]

    # In-flight task is immediately blocked
    c2 = client.post(
        "/api/v1/security/policy-snapshot/assert-tool",
        json={"task_id": "task_hotkill_test", "tool_name": "read_file"},
    )
    assert c2.json()["allowed"] is False
    assert "blocked by active emergency hot-kill" in c2.json()["blocked_reason"]

    # Revoke emergency hot kill
    rev_resp = client.post(
        "/api/v1/security/policy-snapshot/revoke-emergency-hot-kill",
        json={"directive_id": directive_id},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["revoked"] is True

    # In-flight task access restored
    c3 = client.post(
        "/api/v1/security/policy-snapshot/assert-tool",
        json={"task_id": "task_hotkill_test", "tool_name": "read_file"},
    )
    assert c3.json()["allowed"] is True
