"""Integration tests for Pre-Action Side-Effect Gate and Acceptance API endpoints.

[POS]
Tests REST endpoints for:
1. Listing and querying intercepted pre-action challenges.
2. Submitting human decision (approve/reject) and issuing execution tokens.
3. Recording and querying idempotency execution receipts.
4. Running deterministic quality acceptance evaluation on deliverables.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.approvals.side_effect import router as side_effect_router
from app.services.approvals.side_effect_gate_service import (
    get_side_effect_gate_service,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting side-effects router."""
    test_app = FastAPI(title="Side-Effect Gate API Test App")
    test_app.include_router(side_effect_router, prefix="/api/v1/approvals")
    return TestClient(test_app, raise_server_exceptions=False)


def test_side_effect_api_intercept_decide_flow(client: TestClient) -> None:
    service = get_side_effect_gate_service()
    session_id = "sess_api_test_001"
    tool_name = "send_email"
    args = {"to": "partner@global.com", "subject": "Contract Renewal"}

    # Simulate harness intercepting mutating tool call
    eval_res = service.evaluate_tool_action(session_id, tool_name, args)
    assert eval_res.challenge is not None
    challenge_id = eval_res.challenge.challenge_id

    # 1. GET pending challenges
    pending_resp = client.get("/api/v1/approvals/side-effects/pending")
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(c["challenge_id"] == challenge_id for c in pending_list)

    # 2. GET specific challenge
    detail_resp = client.get(f"/api/v1/approvals/side-effects/{challenge_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["challenge_id"] == challenge_id
    assert detail["tool_name"] == tool_name

    # 3. POST decision: approve
    decide_resp = client.post(
        f"/api/v1/approvals/side-effects/{challenge_id}/decide",
        json={
            "decision": "approve",
            "reviewer_id": "auditor_bob",
            "reason": "Authorized by business executive",
        },
    )
    assert decide_resp.status_code == 200
    decision_data = decide_resp.json()
    assert decision_data["status"] == "approved"
    assert decision_data["auth_token"] is not None
    assert decision_data["auth_token"].startswith("tok_")

    # 4. Verified consumed from pending
    pending_resp_after = client.get("/api/v1/approvals/side-effects/pending")
    assert pending_resp_after.status_code == 200
    assert not any(c["challenge_id"] == challenge_id for c in pending_resp_after.json())


def test_side_effect_api_receipt_and_acceptance(client: TestClient) -> None:
    idempotency_key = "idem_api_test_key_999888111"

    # 1. POST record execution receipt
    receipt_payload = {
        "idempotency_key": idempotency_key,
        "tool_name": "stripe_charge",
        "provider_receipt_id": "ch_api_charge_12345",
        "output_summary": "Charge succeeded",
        "challenge_id": None,
    }
    create_rcpt_resp = client.post(
        "/api/v1/approvals/side-effects/receipts",
        json=receipt_payload,
    )
    assert create_rcpt_resp.status_code == 201
    created_receipt = create_rcpt_resp.json()
    assert created_receipt["provider_receipt_id"] == "ch_api_charge_12345"

    # 2. GET query execution receipt
    query_resp = client.get(f"/api/v1/approvals/side-effects/receipts/{idempotency_key}")
    assert query_resp.status_code == 200
    fetched = query_resp.json()
    assert fetched["idempotency_key"] == idempotency_key

    # 3. POST run post-run deterministic acceptance evaluation
    acceptance_payload = {
        "text_content": "# Summary\nAll deliverables met.\n\n## Results\n100% test pass rate.",
        "rules": [
            {
                "rule_type": "non_empty",
                "description": "Non empty check",
            },
            {
                "rule_type": "required_structure",
                "description": "Required markdown sections",
                "required_sections": ["# Summary", "## Results"],
            },
        ],
    }
    accept_resp = client.post(
        "/api/v1/approvals/side-effects/acceptance/evaluate",
        json=acceptance_payload,
    )
    assert accept_resp.status_code == 200
    report = accept_resp.json()
    assert report["passed"] is True
    assert len(report["violations"]) == 0
