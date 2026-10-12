"""
[POS] tests/api/security/test_hardened_sandbox_perimeter_endpoints.py
[INPUT] app.api.security.hardened_sandbox_perimeter_router, app.services.security.hardened_sandbox_perimeter_service
[OUTPUT] endpoint tests

API endpoint tests for Scale-Ready Hardened Agent Sandbox & Safety Perimeter Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.hardened_sandbox_perimeter_router import (
    router as hardened_sandbox_perimeter_router,
)
from app.services.security.hardened_sandbox_perimeter_service import (
    HardenedSandboxPerimeterService,
    get_hardened_sandbox_perimeter_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = HardenedSandboxPerimeterService()
    # Pre-register a secret for ticket minting tests
    test_service.register_master_secret("test_api_key", "sk-secret-vault-token-1234")
    app = FastAPI()
    app.include_router(hardened_sandbox_perimeter_router)
    app.dependency_overrides[get_hardened_sandbox_perimeter_service] = lambda: test_service
    return TestClient(app)


def test_validate_spec_endpoint(client: TestClient) -> None:
    """Test POST /hardened-sandbox/validate-spec."""
    # 1. Valid spec
    valid_payload = {
        "isolation_mode": "CONTAINER",
        "is_non_root": True,
        "uid": 1000,
        "gid": 1000,
        "read_only_rootfs": True,
        "tmpfs_noexec": True,
        "persistent_volume_path": "/workspace",
        "memory_limit_mb": 512,
        "cpu_quota_pct": 1.0,
        "pids_max": 128,
    }
    resp1 = client.post("/hardened-sandbox/validate-spec", json=valid_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_valid"] is True
    assert data1["verdict"] == "VALID"
    assert len(data1["violations"]) == 0

    # 2. Insecure root execution
    invalid_payload = {
        "isolation_mode": "CONTAINER",
        "is_non_root": False,
        "uid": 1,
        "gid": 1,
        "read_only_rootfs": False,
        "tmpfs_noexec": True,
        "persistent_volume_path": "/workspace",
        "memory_limit_mb": 512,
        "cpu_quota_pct": 1.0,
        "pids_max": 128,
    }
    resp2 = client.post("/hardened-sandbox/validate-spec", json=invalid_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_valid"] is False
    assert data2["verdict"] == "INVALID_ROOT_USER"
    assert len(data2["violations"]) >= 1


def test_evaluate_egress_endpoint(client: TestClient) -> None:
    """Test POST /hardened-sandbox/evaluate-egress."""
    # Cloud metadata intercept
    resp_meta = client.post(
        "/hardened-sandbox/evaluate-egress",
        json={"host": "169.254.169.254", "port": 80, "scheme": "http"},
    )
    assert resp_meta.status_code == 200
    data_meta = resp_meta.json()
    assert data_meta["is_allowed"] is False
    assert data_meta["verdict"] == "BLOCKED_CLOUD_METADATA"

    # Private IP intercept
    resp_priv = client.post(
        "/hardened-sandbox/evaluate-egress",
        json={"host": "10.0.0.1", "port": 443, "scheme": "https"},
    )
    assert resp_priv.status_code == 200
    data_priv = resp_priv.json()
    assert data_priv["is_allowed"] is False
    assert data_priv["verdict"] == "BLOCKED_PRIVATE_IP"


def test_credentials_ticket_endpoints(client: TestClient) -> None:
    """Test POST /hardened-sandbox/credentials/mint-ticket and verify-ticket."""
    mint_payload = {
        "secret_alias": "test_api_key",
        "allowed_scopes": ["tool:bash", "tool:fetch"],
        "ttl_seconds": 300.0,
    }
    mint_resp = client.post("/hardened-sandbox/credentials/mint-ticket", json=mint_payload)
    assert mint_resp.status_code == 200
    mint_data = mint_resp.json()
    assert mint_data["ticket_id"].startswith("tkt-")
    assert mint_data["secret_alias"] == "test_api_key"
    assert "tool:bash" in mint_data["allowed_scopes"]

    # Verify ticket with matching scope
    verify_resp_good = client.post(
        "/hardened-sandbox/credentials/verify-ticket",
        json={"ticket_id": mint_data["ticket_id"], "required_scope": "tool:bash"},
    )
    assert verify_resp_good.status_code == 200
    assert verify_resp_good.json()["is_valid"] is True

    # Verify ticket with ungranted scope
    verify_resp_bad = client.post(
        "/hardened-sandbox/credentials/verify-ticket",
        json={"ticket_id": mint_data["ticket_id"], "required_scope": "tool:delete_db"},
    )
    assert verify_resp_bad.status_code == 200
    assert verify_resp_bad.json()["is_valid"] is False


def test_process_guard_endpoints(client: TestClient) -> None:
    """Test POST /hardened-sandbox/process-guard/evaluate and reset."""
    agent_id = "agent-guard-api-test"

    # Safe usage
    eval_resp = client.post(
        "/hardened-sandbox/process-guard/evaluate",
        json={
            "agent_id": agent_id,
            "active_pids_count": 8,
            "memory_used_mb": 96.0,
            "cpu_percent": 10.0,
            "pids_max": 64,
            "memory_limit_mb": 512.0,
        },
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["is_safe"] is True

    # Fork-bomb surge
    eval_resp_fb = client.post(
        "/hardened-sandbox/process-guard/evaluate",
        json={
            "agent_id": agent_id,
            "active_pids_count": 99,
            "memory_used_mb": 200.0,
            "cpu_percent": 90.0,
            "pids_max": 64,
            "memory_limit_mb": 512.0,
        },
    )
    assert eval_resp_fb.status_code == 200
    assert eval_resp_fb.json()["is_safe"] is False
    assert eval_resp_fb.json()["is_circuit_broken"] is True

    # Reset
    reset_resp = client.post(f"/hardened-sandbox/process-guard/reset/{agent_id}")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["was_reset"] is True


def test_metrics_endpoint(client: TestClient) -> None:
    """Test GET /hardened-sandbox/metrics."""
    resp = client.get("/hardened-sandbox/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_spec_validations" in data
    assert "ssrf_blocks" in data
    assert "credential_tickets_minted" in data
    assert "fork_bomb_mitigations" in data
