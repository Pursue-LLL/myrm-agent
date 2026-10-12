"""
Integration tests for Short-Lived Ticket Session Exchange & Subdomain Isolated Gateway REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.subdomain_ticket_gateway_router import (
    router as subdomain_ticket_gateway_router,
)
from app.services.security.subdomain_ticket_gateway_service import (
    SubdomainTicketGatewayService,
    get_subdomain_ticket_gateway_service,
)


@pytest.fixture
def client() -> TestClient:
    service = SubdomainTicketGatewayService()
    app = FastAPI()
    app.include_router(subdomain_ticket_gateway_router)
    app.dependency_overrides[get_subdomain_ticket_gateway_service] = lambda: service
    return TestClient(app)


def test_endpoint_ticket_issue_and_redeem(client: TestClient) -> None:
    # 1. Issue ticket
    issue_resp = client.post(
        "/subdomain-ticket-gateway/tickets/issue",
        json={
            "master_user_id": "usr-corp-admin",
            "target_instance_id": "inst-prod-007",
            "client_ip": "10.0.0.1",
            "client_fingerprint": "canvas-fp-9988",
        },
    )
    assert issue_resp.status_code == 200
    tkt_data = issue_resp.json()
    ticket_id = tkt_data["ticket_id"]
    assert ticket_id.startswith("tkt-")

    # 2. Redeem ticket
    redeem_resp = client.post(
        "/subdomain-ticket-gateway/tickets/redeem",
        json={
            "ticket_id": ticket_id,
            "client_ip": "10.0.0.1",
            "client_fingerprint": "canvas-fp-9988",
        },
    )
    assert redeem_resp.status_code == 200
    redeem_data = redeem_resp.json()
    assert redeem_data["status"] == "VALID"
    assert redeem_data["session"] is not None
    assert redeem_data["session"]["instance_id"] == "inst-prod-007"

    # 3. Replay must be blocked
    replay_resp = client.post(
        "/subdomain-ticket-gateway/tickets/redeem",
        json={
            "ticket_id": ticket_id,
            "client_ip": "10.0.0.1",
            "client_fingerprint": "canvas-fp-9988",
        },
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["status"] == "ALREADY_CONSUMED"


def test_endpoint_session_validation_and_revocation(client: TestClient) -> None:
    # Issue & Redeem
    issue_resp = client.post(
        "/subdomain-ticket-gateway/tickets/issue",
        json={
            "master_user_id": "usr-corp-user",
            "target_instance_id": "inst-worker-1",
            "client_ip": "192.168.0.50",
            "client_fingerprint": "fingerprint-aaa",
        },
    )
    ticket_id = issue_resp.json()["ticket_id"]
    redeem_resp = client.post(
        "/subdomain-ticket-gateway/tickets/redeem",
        json={
            "ticket_id": ticket_id,
            "client_ip": "192.168.0.50",
            "client_fingerprint": "fingerprint-aaa",
        },
    )
    session_id = redeem_resp.json()["session"]["session_id"]

    # Validate
    val_resp = client.post(
        "/subdomain-ticket-gateway/sessions/validate",
        json={
            "session_id": session_id,
            "instance_id": "inst-worker-1",
        },
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["is_valid"]

    # Revoke
    rev_resp = client.post(
        "/subdomain-ticket-gateway/sessions/revoke",
        json={"session_id": session_id},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["success"]

    # Re-validate
    reval_resp = client.post(
        "/subdomain-ticket-gateway/sessions/validate",
        json={
            "session_id": session_id,
            "instance_id": "inst-worker-1",
        },
    )
    assert not reval_resp.json()["is_valid"]


def test_endpoint_airgap_evaluation_and_metrics(client: TestClient) -> None:
    # Block control plane endpoint
    block_resp = client.post(
        "/subdomain-ticket-gateway/airgap/evaluate",
        json={
            "current_instance_id": "inst-worker-1",
            "requested_path": "/api/v1/admin/tenants",
        },
    )
    assert block_resp.status_code == 200
    assert not block_resp.json()["is_allowed"]
    assert block_resp.json()["verdict"] == "BLOCKED_MASTER_CONTROL_PLANE_ATTEMPT"

    # Allow local sandbox endpoint
    allow_resp = client.post(
        "/subdomain-ticket-gateway/airgap/evaluate",
        json={
            "current_instance_id": "inst-worker-1",
            "requested_path": "/api/v1/tools/run",
            "target_instance_id": "inst-worker-1",
        },
    )
    assert allow_resp.status_code == 200
    assert allow_resp.json()["is_allowed"]
    assert allow_resp.json()["verdict"] == "ALLOWED_SANDBOX_LOCAL"

    # Query metrics
    metrics_resp = client.get("/subdomain-ticket-gateway/metrics")
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert "tickets_issued_total" in m
    assert "tickets_redeemed_total" in m
    assert "replay_attacks_blocked_total" in m
    assert "airgap_violations_blocked_total" in m
    assert "active_sessions_total" in m
