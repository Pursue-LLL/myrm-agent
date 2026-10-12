"""Integration tests for Dual-Track Soft Memory vs Hard Redline Sandbox Guard API endpoints."""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.dual_track_sandbox_guard_router import (
    router as dual_track_sandbox_guard_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting dual_track_sandbox_guard_router."""
    test_app = FastAPI(title="Dual Track Sandbox Guard Test App")
    test_app.include_router(dual_track_sandbox_guard_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_evaluate_file_execution_endpoint(client: TestClient) -> None:
    # 1. Blocked protected file
    req_file_blocked = {
        "operation_type": "file",
        "target": "server/.env.local",
        "sub_operation": "read",
    }
    resp_b = client.post(
        "/api/v1/security/dual-track-sandbox-guard/evaluate-execution",
        json=req_file_blocked,
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["is_permitted"] is False
    assert data_b["verdict"] == "BLOCKED_HARD_REDLINE_FILE"

    # 2. Permitted file
    req_file_ok = {
        "operation_type": "file",
        "target": "src/components/Button.tsx",
        "sub_operation": "write",
    }
    resp_ok = client.post(
        "/api/v1/security/dual-track-sandbox-guard/evaluate-execution",
        json=req_file_ok,
    )
    assert resp_ok.status_code == 200
    data_ok = resp_ok.json()
    assert data_ok["is_permitted"] is True
    assert data_ok["verdict"] == "PERMITTED"


def test_evaluate_command_execution_endpoint(client: TestClient) -> None:
    # 1. Catastrophic command
    req_cmd_rm = {
        "operation_type": "command",
        "target": "rm -rf /",
    }
    resp_rm = client.post(
        "/api/v1/security/dual-track-sandbox-guard/evaluate-execution",
        json=req_cmd_rm,
    )
    assert resp_rm.status_code == 200
    assert resp_rm.json()["is_permitted"] is False
    assert resp_rm.json()["verdict"] == "BLOCKED_HARD_REDLINE_COMMAND"

    # 2. Obfuscation evasion
    encoded = base64.b64encode(b"cat /etc/shadow").decode("ascii")
    req_cmd_evasion = {
        "operation_type": "command",
        "target": f"echo '{encoded}' | base64 -d | sh",
    }
    resp_ev = client.post(
        "/api/v1/security/dual-track-sandbox-guard/evaluate-execution",
        json=req_cmd_evasion,
    )
    assert resp_ev.status_code == 200
    assert resp_ev.json()["is_permitted"] is False
    assert resp_ev.json()["verdict"] == "BLOCKED_EVASION_ATTEMPT"

    # 3. Permitted command
    req_cmd_safe = {
        "operation_type": "command",
        "target": "cargo check",
    }
    resp_safe = client.post(
        "/api/v1/security/dual-track-sandbox-guard/evaluate-execution",
        json=req_cmd_safe,
    )
    assert resp_safe.status_code == 200
    assert resp_safe.json()["is_permitted"] is True
    assert resp_safe.json()["verdict"] == "PERMITTED"


def test_policy_summary_and_register_rule_endpoints(client: TestClient) -> None:
    # 1. Get compiled policy
    resp_pol = client.get("/api/v1/security/dual-track-sandbox-guard/compiled-policy")
    assert resp_pol.status_code == 200
    pol_data = resp_pol.json()
    assert pol_data["rule_count"] >= 10
    assert len(pol_data["blocked_file_patterns"]) > 0

    # 2. List rules
    resp_rules = client.get("/api/v1/security/dual-track-sandbox-guard/rules")
    assert resp_rules.status_code == 200
    assert len(resp_rules.json()) >= 10

    # 3. Register custom rule
    new_rule_req = {
        "rule_id": "RL-CMD-777",
        "category": "COMMAND_PROTECTION",
        "pattern": r"\bdd\s+if=/dev/zero",
        "description": "Block disk zeroing dd operations",
        "severity": "CRITICAL",
    }
    resp_reg = client.post(
        "/api/v1/security/dual-track-sandbox-guard/register-rule",
        json=new_rule_req,
    )
    assert resp_reg.status_code == 200
    assert resp_reg.json()["rule_id"] == "RL-CMD-777"
