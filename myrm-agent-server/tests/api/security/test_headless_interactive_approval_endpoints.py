"""API endpoint tests for Headless Agent Interactive Approval, Webhook Relay, and Hold-Resume Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.headless_interactive_approval_router import (
    router as headless_interactive_approval_router,
)
from app.services.security.headless_interactive_approval_service import (
    HeadlessInteractiveApprovalService,
    get_headless_approval_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = HeadlessInteractiveApprovalService(base_approval_url="https://secops.example.com/approve")
    app = FastAPI()
    app.include_router(headless_interactive_approval_router)
    app.dependency_overrides[get_headless_approval_service] = lambda: test_service
    return TestClient(app)


def test_hold_ticket_create_and_get_endpoints(client: TestClient) -> None:
    # 1. Create ticket
    resp_create = client.post(
        "/headless-approval/hold-tickets/create",
        json={
            "session_id": "session_api_hl_01",
            "action": {
                "action_id": "act_rm_rf",
                "tool_name": "bash",
                "command_or_target": "rm -rf /var/cache/app",
                "risk_level": "CRITICAL",
                "justification": "Purge cache directory",
            },
            "timeout_seconds": 180.0,
        },
    )
    assert resp_create.status_code == 201
    ticket = resp_create.json()
    tx_id = ticket["tx_id"]
    assert tx_id.startswith("tx-")
    assert ticket["status"] == "PENDING"
    assert "https://secops.example.com/approve?tx=" in ticket["shortlink_url"]

    # 2. Get ticket
    resp_get = client.get(f"/headless-approval/hold-tickets/{tx_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["tx_id"] == tx_id
    assert resp_get.json()["action"]["tool_name"] == "bash"

    # 3. Not found
    resp_404 = client.get("/headless-approval/hold-tickets/tx-nonexistent")
    assert resp_404.status_code == 404


def test_submit_decision_endpoint(client: TestClient) -> None:
    # 1. Create ticket
    resp_create = client.post(
        "/headless-approval/hold-tickets/create",
        json={
            "session_id": "session_api_hl_02",
            "action": {
                "action_id": "act_deploy",
                "tool_name": "k8s_client",
                "command_or_target": "kubectl delete deployment nginx-prod",
                "risk_level": "CRITICAL",
                "justification": "Scale down production deployment",
            },
        },
    )
    tx_id = resp_create.json()["tx_id"]

    # 2. Submit APPROVED decision
    resp_decision = client.post(
        f"/headless-approval/hold-tickets/{tx_id}/decision",
        json={
            "decision": "APPROVED",
            "operator": "devops_charlie",
            "notes": "Verified off-peak change window.",
        },
    )
    assert resp_decision.status_code == 200
    decision_data = resp_decision.json()
    assert decision_data["resumed"] is True
    assert decision_data["ticket"]["status"] == "APPROVED"
    assert decision_data["ticket"]["decided_by"] == "devops_charlie"

    # 3. Bad request on invalid decision
    resp_invalid = client.post(
        f"/headless-approval/hold-tickets/{tx_id}/decision",
        json={"decision": "MAYBE", "operator": "devops_charlie"},
    )
    assert resp_invalid.status_code == 400


def test_webhooks_and_relay_endpoints(client: TestClient) -> None:
    # 1. Register webhook endpoint
    resp_reg = client.post(
        "/headless-approval/webhooks/endpoints",
        json={
            "name": "pagerduty_stream",
            "url": "https://events.pagerduty.com/v2/enqueue",
        },
    )
    assert resp_reg.status_code == 200
    assert "pagerduty_stream" in resp_reg.json()

    # 2. List endpoints
    resp_list = client.get("/headless-approval/webhooks/endpoints")
    assert resp_list.status_code == 200
    assert "pagerduty_stream" in resp_list.json()

    # 3. Get relay payload
    resp_ticket = client.post(
        "/headless-approval/hold-tickets/create",
        json={
            "session_id": "session_api_hl_03",
            "action": {
                "action_id": "act_publish",
                "tool_name": "twitter_api",
                "command_or_target": "POST https://api.twitter.com/tweets",
                "risk_level": "HIGH",
                "justification": "Publish release announcement",
            },
        },
    )
    tx_id = resp_ticket.json()["tx_id"]

    resp_payload = client.get(f"/headless-approval/hold-tickets/{tx_id}/relay-payload")
    assert resp_payload.status_code == 200
    payload = resp_payload.json()
    assert payload["tx_id"] == tx_id
    assert payload["tool_name"] == "twitter_api"
    assert "https://secops.example.com/approve?tx=" in payload["approval_shortlink"]


def test_stream_notice_endpoint(client: TestClient) -> None:
    resp_ticket = client.post(
        "/headless-approval/hold-tickets/create",
        json={
            "session_id": "session_api_hl_04",
            "action": {
                "action_id": "act_s3_delete",
                "tool_name": "s3_manager",
                "command_or_target": "s3://prod-backups/daily.tar.gz",
                "risk_level": "CRITICAL",
                "justification": "Prune old backup",
            },
        },
    )
    tx_id = resp_ticket.json()["tx_id"]

    # Format hold reasoning chunk
    resp_notice = client.post(
        "/headless-approval/stream-notice",
        json={"tx_id": tx_id, "is_resumed": False},
    )
    assert resp_notice.status_code == 200
    chunk = resp_notice.json()
    assert chunk["tx_id"] == tx_id
    assert chunk["is_resumed"] is False
    assert "安全挂起" in chunk["inject_markdown"]
