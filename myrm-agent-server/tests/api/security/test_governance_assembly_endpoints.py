"""Integration tests for Governance Assembly API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.governance_assembly_router import router as governance_assembly_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting governance_assembly_router."""
    test_app = FastAPI(title="Governance Assembly Test App")
    test_app.include_router(governance_assembly_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_record_invocation_and_matrix_report_endpoints(client: TestClient) -> None:
    client.post("/api/v1/security/governance-assembly/reset")

    # 1. Record an invocation
    inv_payload = {
        "tool_name": "query_inventory",
        "ingress_source": "INTERACTIVE_CHAT",
        "applied_middlewares": ["EStopCheck", "LoopGuard", "ToolInterceptorMiddleware", "TripartiteLedgerGate"],
        "is_governed": True,
        "call_stack_summary": "chat_router -> agent -> query_inventory",
    }
    resp = client.post("/api/v1/security/governance-assembly/invocations", json=inv_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tool_name"] == "query_inventory"
    assert data["is_governed"] is True
    assert data["ingress_source"] == "INTERACTIVE_CHAT"

    # 2. Get matrix report
    rep_resp = client.get("/api/v1/security/governance-assembly/matrix-report")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert rep_data["total_invocations"] == 1
    assert rep_data["governed_invocations"] == 1
    assert rep_data["is_fully_compliant"] is True
    assert rep_data["coverage_ratio"] == 1.0


def test_verify_tool_endpoint(client: TestClient) -> None:
    # 1. Verify compliant tool
    v_resp = client.post(
        "/api/v1/security/governance-assembly/verify-tool",
        json={
            "tool_name": "db_read",
            "applied_middlewares": ["EStopCheck", "LoopGuard", "ToolInterceptorMiddleware", "TripartiteLedgerGate"],
        },
    )
    assert v_resp.status_code == 200
    assert v_resp.json()["is_valid"] is True

    # 2. Verify non-compliant tool
    iv_resp = client.post(
        "/api/v1/security/governance-assembly/verify-tool",
        json={
            "tool_name": "db_write",
            "applied_middlewares": ["EStopCheck"],
        },
    )
    assert iv_resp.status_code == 200
    assert iv_resp.json()["is_valid"] is False
    assert "TripartiteLedgerGate" in iv_resp.json()["missing_middlewares"]


def test_simulate_workflow_endpoint(client: TestClient) -> None:
    client.post("/api/v1/security/governance-assembly/reset")

    # 1. Fully governed simulation
    sim_resp = client.post(
        "/api/v1/security/governance-assembly/simulate-workflow",
        json={
            "scenario_name": "cron_sync",
            "ingress_source": "BACKGROUND_CRON",
            "tools": ["pull_data", "process_data"],
            "simulate_naked_tool": False,
        },
    )
    assert sim_resp.status_code == 200
    data = sim_resp.json()
    assert data["is_governed"] is True
    assert len(data["executed_tools"]) == 2

    # 2. Naked tool detection
    naked_resp = client.post(
        "/api/v1/security/governance-assembly/simulate-workflow",
        json={
            "scenario_name": "subagent_attack",
            "ingress_source": "SUBAGENT_DAG",
            "tools": ["safe_step", "naked_bypass"],
            "simulate_naked_tool": True,
        },
    )
    assert naked_resp.status_code == 200
    naked_data = naked_resp.json()
    assert naked_data["is_governed"] is False
    assert any("[BLOCKED_BY_WATCHDOG]" in r for r in naked_data["results"])
