"""Integration tests for Financial Sign-Off Gate API endpoints and Decision-to-Receipt binding."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.approvals.financial import router as financial_router
from app.schemas.local_action_audit import ActionSurface


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting financial sign-off router."""
    test_app = FastAPI(title="Financial Sign-Off Gate Test App")
    test_app.include_router(financial_router, prefix="/api/v1/approvals")
    return TestClient(test_app, raise_server_exceptions=False)


@pytest.mark.asyncio
async def test_financial_gate_api_full_three_stage_chain(client: TestClient) -> None:
    """Validate three-stage chain: Draft Action Surface -> Human Sign-Off -> Delivery Receipt Binding."""
    # 1. POST create draft
    fin_details = {
        "amount": 3499.00,
        "currency": "USD",
        "payee_account": "ACH-ROUTING-789-ACCT-9921",
        "payee_name": "DataCenter Colocation Services",
        "purpose": "Monthly GPU server lease for agent worker pool",
    }
    action_digest = ActionSurface.compute_digest("payment_transfer", str(fin_details))
    draft_payload = {
        "agent_id": "agent-treasury",
        "action_surface": {
            "action_type": "payment_transfer",
            "financial_details": fin_details,
            "action_digest": action_digest,
        },
        "plan": {
            "steps": ["Step 1: Check balance", "Step 2: Transfer $3,499.00 USD"],
            "risk_assessment": "High impact direct bank debit",
            "estimated_impact": "Operational expense deduction",
            "fail_closed": True,
        },
        "session_id": "sess-fin-101",
        "task_id": "task-colocation-lease",
    }

    create_resp = client.post("/api/v1/approvals/financial/drafts", json=draft_payload)
    assert create_resp.status_code == 200
    draft_data = create_resp.json()
    draft_id = draft_data["draft_id"]
    assert draft_data["status"] == "PENDING_SIGNOFF"
    assert draft_data["action_surface"]["action_digest"] == action_digest

    # 2. GET drafts list and single detail
    list_resp = client.get("/api/v1/approvals/financial/drafts?agent_id=agent-treasury&status=PENDING_SIGNOFF")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    detail_resp = client.get(f"/api/v1/approvals/financial/drafts/{draft_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["draft_id"] == draft_id

    # 3. POST human sign-off: APPROVE
    signoff_payload = {
        "operator_id": "vp-finance-carol",
        "decision": "APPROVE",
    }
    signoff_resp = client.post(f"/api/v1/approvals/financial/drafts/{draft_id}/signoff", json=signoff_payload)
    assert signoff_resp.status_code == 200
    approved_data = signoff_resp.json()
    assert approved_data["status"] == "APPROVED"
    assert approved_data["operator_id"] == "vp-finance-carol"
    assert approved_data["signoff_token"] is not None

    # 4. POST bind delivery receipt (Completing Decision-to-Receipt three-stage chain)
    receipt_payload = {
        "external_reference_id": "fedwire_txn_20261005_9999",
        "delivery_status": "SETTLED",
        "response_data": '{"settlement": "confirmed", "fedwire_id": "20261005_9999"}',
    }
    receipt_resp = client.post(
        f"/api/v1/approvals/financial/drafts/{draft_id}/delivery-receipt",
        json=receipt_payload,
    )
    assert receipt_resp.status_code == 200
    receipt_data = receipt_resp.json()
    assert receipt_data["approval_id"] == draft_id
    assert receipt_data["delivery_status"] == "SETTLED"
    assert receipt_data["external_reference_id"] == "fedwire_txn_20261005_9999"

    # 5. Check updated draft status is EXECUTED and contains delivery receipt
    final_detail_resp = client.get(f"/api/v1/approvals/financial/drafts/{draft_id}")
    assert final_detail_resp.status_code == 200
    final_draft = final_detail_resp.json()
    assert final_draft["status"] == "EXECUTED"
    assert final_draft["delivery_receipt"] is not None
    assert final_draft["delivery_receipt"]["delivery_receipt_id"] == receipt_data["delivery_receipt_id"]


@pytest.mark.asyncio
async def test_financial_gate_api_rejection_and_errors(client: TestClient) -> None:
    """Validate error handling for 404s, invalid status transitions, and rejections."""
    # 404 for unknown draft
    resp = client.get("/api/v1/approvals/financial/drafts/non-existent-id")
    assert resp.status_code == 404

    # Create email draft
    email_details = {
        "recipients": ["ceo@competitor.com"],
        "cc": [],
        "subject": "Confidential Product Roadmap Q4",
        "body_preview": "Here are our unannounced secret features...",
        "has_attachments": True,
    }
    digest = ActionSurface.compute_digest("send_email", str(email_details))
    payload = {
        "agent_id": "agent-outbound",
        "action_surface": {
            "action_type": "send_email",
            "email_details": email_details,
            "action_digest": digest,
        },
        "plan": {
            "steps": ["Send email to external address"],
            "risk_assessment": "Extreme PII / Confidential leakage risk",
            "estimated_impact": "Irreversible external disclosure",
            "fail_closed": True,
        },
    }
    create_resp = client.post("/api/v1/approvals/financial/drafts", json=payload)
    assert create_resp.status_code == 200
    draft_id = create_resp.json()["draft_id"]

    # Reject draft
    reject_resp = client.post(
        f"/api/v1/approvals/financial/drafts/{draft_id}/signoff",
        json={
            "operator_id": "security-officer-dan",
            "decision": "REJECT",
            "rejection_reason": "Confidential information cannot be sent externally",
        },
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"

    # Attempting to bind delivery receipt to rejected draft should return 400
    bad_receipt_resp = client.post(
        f"/api/v1/approvals/financial/drafts/{draft_id}/delivery-receipt",
        json={
            "delivery_status": "DELIVERED",
            "response_data": "{}",
        },
    )
    assert bad_receipt_resp.status_code == 400
