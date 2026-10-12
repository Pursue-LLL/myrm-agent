"""Integration tests for Tripartite Isolation & Immutable Audit Ledger API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.tripartite_ledger_router import router as tripartite_ledger_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting tripartite_ledger_router."""
    test_app = FastAPI(title="Tripartite Ledger Test App")
    test_app.include_router(tripartite_ledger_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_append_verify_query_endpoints(client: TestClient) -> None:
    # 1. Append record
    payload = {
        "who_user_id": "usr_99",
        "who_agent_id": "agt_data",
        "rule_version_hash": "sha256_ruleset",
        "tool_name": "mcp__snowflake__query",
        "tool_args": {"sql": "SELECT 1", "api_token": "token_abc"},
        "connector_source": "mcp__snowflake",
        "connector_scope": "warehouse:query",
        "authorized_parameters": ["sql"],
        "reconcile_receipt": "rcpt_sf_1",
    }
    resp = client.post("/api/v1/security/tripartite-ledger/records", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["who_user_id"] == "usr_99"
    assert data["who_agent_id"] == "agt_data"
    assert data["sanitized_args_snapshot"]["api_token"] == "[REDACTED_SECRET]"
    rec_id = data["record_id"]

    # 2. Verify ledger
    v_resp = client.get("/api/v1/security/tripartite-ledger/verify")
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["is_valid"] is True
    assert v_data["total_records"] >= 1

    # 3. Query records
    q_resp = client.post(
        "/api/v1/security/tripartite-ledger/query",
        json={"connector_source": "mcp__snowflake", "who_agent_id": "agt_data"},
    )
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["total_matched"] >= 1
    assert any(r["record_id"] == rec_id for r in q_data["records"])


def test_action_semantics_execution_endpoints(client: TestClient) -> None:
    # 1. REPLAY_LOG blocks
    replay_resp = client.post(
        "/api/v1/security/tripartite-ledger/execute",
        json={"mode": "REPLAY_LOG", "tool_name": "transfer_funds"},
    )
    assert replay_resp.status_code == 400
    assert "strictly forbids" in replay_resp.json()["detail"]

    # 2. OFFLINE_EVAL simulates
    eval_resp = client.post(
        "/api/v1/security/tripartite-ledger/execute",
        json={"mode": "OFFLINE_EVAL", "tool_name": "transfer_funds"},
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["is_simulated"] is True
    assert eval_data["executed"] is False

    # 3. RE_EXECUTE unconfirmed rejected
    unconf_resp = client.post(
        "/api/v1/security/tripartite-ledger/execute",
        json={"mode": "RE_EXECUTE", "tool_name": "transfer_funds", "explicit_confirmed": False},
    )
    assert unconf_resp.status_code == 400

    # 4. RE_EXECUTE without pre-I/O audit record rejected with 403
    unrec_resp = client.post(
        "/api/v1/security/tripartite-ledger/execute",
        json={
            "mode": "RE_EXECUTE",
            "tool_name": "transfer_funds",
            "explicit_confirmed": True,
            "audit_record_id": "aud_non_existent",
        },
    )
    assert unrec_resp.status_code == 403
    assert "must be committed" in unrec_resp.json()["detail"]

    # 5. Pre-record audit, then RE_EXECUTE succeeds
    app_resp = client.post(
        "/api/v1/security/tripartite-ledger/records",
        json={
            "who_user_id": "usr_cfo",
            "who_agent_id": "agt_pay",
            "rule_version_hash": "v1",
            "tool_name": "transfer_funds",
            "tool_args": {"amount": 1000},
            "connector_source": "mcp__bank",
            "connector_scope": "payments",
            "authorized_parameters": ["amount"],
            "reconcile_receipt": "rcpt_prep",
        },
    )
    pre_rec_id = app_resp.json()["record_id"]

    exec_resp = client.post(
        "/api/v1/security/tripartite-ledger/execute",
        json={
            "mode": "RE_EXECUTE",
            "tool_name": "transfer_funds",
            "explicit_confirmed": True,
            "audit_record_id": pre_rec_id,
        },
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["executed"] is True
    assert exec_resp.json()["audit_record_id"] == pre_rec_id


def test_ops_telemetry_and_force_stop_endpoints(client: TestClient) -> None:
    # 1. Register task
    reg_resp = client.post(
        "/api/v1/security/tripartite-ledger/ops/tasks",
        json={"task_id": "task_api_1", "agent_id": "agt_batch"},
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["task_id"] == "task_api_1"
    assert reg_resp.json()["state"] == "RUNNING"

    # 2. Get telemetry
    tel_resp = client.get("/api/v1/security/tripartite-ledger/ops/telemetry/task_api_1")
    assert tel_resp.status_code == 200
    tel_data = tel_resp.json()
    assert tel_data["task_id"] == "task_api_1"
    assert "prompt" not in tel_data
    assert "content" not in tel_data

    # 3. Force stop
    stop_resp = client.post(
        "/api/v1/security/tripartite-ledger/ops/force-stop",
        json={"task_id": "task_api_1", "operator_id": "op_alice"},
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["stopped"] is True

    # Check updated telemetry
    tel_resp2 = client.get("/api/v1/security/tripartite-ledger/ops/telemetry/task_api_1")
    assert tel_resp2.json()["state"] == "STOPPED_BY_OPS"
