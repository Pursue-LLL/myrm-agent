"""Integration tests for Streaming Endpoint Identity Gate Parity API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.streaming_gate_router import (
    router as streaming_gate_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting streaming_gate_router."""
    test_app = FastAPI(title="Streaming Gate Test App")
    test_app.include_router(streaming_gate_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_list_and_register_contracts_endpoint(client: TestClient) -> None:
    # 1. List contracts
    resp = client.get("/api/v1/security/streaming-gate/contracts")
    assert resp.status_code == 200
    contracts = resp.json()
    assert len(contracts) >= 7

    # 2. Register custom contract
    new_contract = {
        "endpoint_path": "/api/v1/custom_events/stream",
        "transport": "SSE",
        "requires_auth": True,
        "required_scope": "custom:read",
        "target_resource_type": "custom",
        "supports_remote_access": True,
    }
    post_resp = client.post("/api/v1/security/streaming-gate/contracts", json=new_contract)
    assert post_resp.status_code == 201
    assert post_resp.json()["endpoint_path"] == "/api/v1/custom_events/stream"


def test_evaluate_access_endpoint(client: TestClient) -> None:
    # 1. Unauthenticated request rejected
    anon_payload = {
        "endpoint_path": "/api/v1/tasks/stream",
        "client_identity": {
            "subject_id": None,
            "auth_source": None,
            "granted_scopes": [],
            "bound_resource_ids": [],
            "is_loopback": False,
            "is_remote": False,
        },
    }
    anon_resp = client.post("/api/v1/security/streaming-gate/evaluate", json=anon_payload)
    assert anon_resp.status_code == 200
    data = anon_resp.json()
    assert data["allowed"] is False
    assert data["verdict"]["decision"] == "DENIED_UNAUTHENTICATED"
    assert data["verdict"]["status_code"] == 401

    # 2. Authorized request approved
    auth_payload = {
        "endpoint_path": "/api/v1/tasks/stream",
        "client_identity": {
            "subject_id": "operator",
            "auth_source": "bearer",
            "granted_scopes": ["tasks:stream"],
            "bound_resource_ids": [],
            "is_loopback": True,
            "is_remote": False,
        },
    }
    auth_resp = client.post("/api/v1/security/streaming-gate/evaluate", json=auth_payload)
    assert auth_resp.status_code == 200
    auth_data = auth_resp.json()
    assert auth_data["allowed"] is True
    assert auth_data["verdict"]["decision"] == "ALLOWED"
    assert auth_data["verdict"]["status_code"] == 200


def test_parity_audit_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/security/streaming-gate/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_endpoints_evaluated" in data
    assert "total_issues_found" in data
    assert "is_compliant" in data
    assert data["is_compliant"] is True
