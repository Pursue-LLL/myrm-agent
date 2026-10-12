"""
Integration tests for Model Degradation Circuit Breaker & Sovereign Governance REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.model_sovereignty_circuit_breaker_router import (
    router as model_sovereignty_circuit_breaker_router,
)
from app.services.security.model_sovereignty_circuit_breaker_service import (
    ModelSovereigntyCircuitBreakerService,
    get_model_sovereignty_circuit_breaker_service,
)


@pytest.fixture
def client() -> TestClient:
    service = ModelSovereigntyCircuitBreakerService()
    app = FastAPI()
    app.include_router(model_sovereignty_circuit_breaker_router)
    app.dependency_overrides[get_model_sovereignty_circuit_breaker_service] = lambda: service
    return TestClient(app)


def test_endpoint_inspect_telemetry_healthy(client: TestClient) -> None:
    resp = client.post(
        "/model-sovereignty-circuit-breaker/inspect-telemetry",
        json={
            "provider_id": "fast-cloud",
            "model_name": "gpt-4o",
            "prompt_tokens": 120,
            "completion_tokens": 400,
            "latency_ms": 650.0,
            "output_text": "Here is the comprehensive response.",
            "expected_tool_call": False,
            "valid_tool_call_produced": True,
            "refusal_detected": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["circuit_state"] == "CLOSED"
    assert not data["did_circuit_trip"]
    assert not data["report"]["is_silent_swap_suspected"]
    assert data["report"]["severity"] == "NORMAL"


def test_endpoint_inspect_telemetry_outage_trips(client: TestClient) -> None:
    payload = {
        "provider_id": "degrading-cloud",
        "model_name": "flaky-llm",
        "prompt_tokens": 100,
        "completion_tokens": 0,
        "latency_ms": 10.0,
        "output_text": "",
        "expected_tool_call": False,
        "valid_tool_call_produced": True,
        "refusal_detected": False,
    }
    # 1st failure
    r1 = client.post("/model-sovereignty-circuit-breaker/inspect-telemetry", json=payload)
    assert r1.status_code == 200
    assert r1.json()["circuit_state"] == "CLOSED"
    assert not r1.json()["did_circuit_trip"]

    # 2nd failure trips circuit
    r2 = client.post("/model-sovereignty-circuit-breaker/inspect-telemetry", json=payload)
    assert r2.status_code == 200
    assert r2.json()["circuit_state"] == "OPEN"
    assert r2.json()["did_circuit_trip"]


def test_endpoint_route_request(client: TestClient) -> None:
    resp = client.post(
        "/model-sovereignty-circuit-breaker/route-request",
        json={
            "provider_id": "test-provider",
            "fallback_target": "backup-local-model",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selected_target"] == "test-provider"
    assert not data["is_fallback"]
    assert data["circuit_state"] == "CLOSED"


def test_endpoint_audit_sovereignty(client: TestClient) -> None:
    resp = client.post(
        "/model-sovereignty-circuit-breaker/audit-sovereignty",
        json={
            "is_data_self_hosted": True,
            "is_model_self_hosted": True,
            "is_tool_sandbox_isolated": True,
            "active_storage_mode": "local_sqlite",
            "active_model_endpoint": "http://127.0.0.1:11434",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sovereignty_score"] == 100
    assert data["is_data_self_hosted"]
    assert data["is_model_self_hosted"]
    assert data["is_tool_sandbox_isolated"]


def test_endpoint_mesh_nodes_crud_and_heartbeat(client: TestClient) -> None:
    # 1. Register node
    reg_resp = client.post(
        "/model-sovereignty-circuit-breaker/mesh-nodes",
        json={
            "node_id": "worker-alpha",
            "hostname": "alpha.internal",
            "node_type": "gpu_worker",
            "capacity_weight": 40,
        },
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json()["node_id"] == "worker-alpha"
    assert reg_resp.json()["is_healthy"]

    # 2. List healthy
    list_resp = client.get("/model-sovereignty-circuit-breaker/mesh-nodes/healthy")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 3. Best node
    best_resp = client.get("/model-sovereignty-circuit-breaker/mesh-nodes/best?preferred_type=gpu_worker")
    assert best_resp.status_code == 200
    assert best_resp.json() is not None
    assert best_resp.json()["node_id"] == "worker-alpha"

    # 4. Heartbeat
    hb_resp = client.post(
        "/model-sovereignty-circuit-breaker/mesh-nodes/heartbeat",
        json={"node_id": "worker-alpha"},
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["success"]


def test_endpoint_reset_circuit_and_metrics(client: TestClient) -> None:
    # Reset
    reset_resp = client.post(
        "/model-sovereignty-circuit-breaker/circuit/reset",
        json={"provider_id": "failing-provider"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["circuit_state"] == "CLOSED"

    # Metrics
    metrics_resp = client.get("/model-sovereignty-circuit-breaker/metrics")
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert "fingerprint_inspections_total" in m
    assert "circuit_trips_total" in m
    assert "fallback_reroutes_total" in m
    assert "sovereign_audits_total" in m
