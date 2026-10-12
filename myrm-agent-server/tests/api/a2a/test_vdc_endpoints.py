"""Integration tests for A2A Verifiable Delegation Credential (VDC) and Negotiation API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.a2a.vdc_router import router as vdc_router
from app.schemas.a2a_vdc import NegotiationTerms
from app.services.a2a.negotiation_ledger import A2ANegotiationLedgerService


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting vdc_router."""
    test_app = FastAPI(title="A2A VDC Test App")
    test_app.include_router(vdc_router, prefix="/api/v1/a2a")
    return TestClient(test_app, raise_server_exceptions=False)


def test_vdc_issue_and_verify_endpoints(client: TestClient) -> None:
    """Validate POST /a2a/vdc/issue and POST /a2a/vdc/verify."""
    # 1. Issue VDC
    issue_payload = {
        "issuer_did": "did:corp:acme-enterprises",
        "issuer_name": "Acme Enterprises Inc.",
        "holder_agent_id": "agent-procurement-007",
        "holder_name": "Procurement Bot 007",
        "max_transaction_amount": 75000.0,
        "allowed_actions": ["quote", "counter_offer", "sign_contract"],
        "validity_duration_seconds": 3600,
        "currency": "USD",
        "issuer_public_key": "acme_pubkey_2026",
    }
    resp = client.post("/api/v1/a2a/vdc/issue", json=issue_payload)
    assert resp.status_code == 200
    vdc_data = resp.json()
    assert vdc_data["credential_id"] != ""
    assert vdc_data["signature"] != ""
    assert vdc_data["max_transaction_amount"] == 75000.0

    # 2. Verify valid proposal
    verify_payload = {
        "vdc": vdc_data,
        "proposed_action": "quote",
        "proposed_amount": 50000.0,
    }
    verify_resp = client.post("/api/v1/a2a/vdc/verify", json=verify_payload)
    assert verify_resp.status_code == 200
    verify_result = verify_resp.json()
    assert verify_result["is_valid"] is True
    assert verify_result["amount_permitted"] is True
    assert verify_result["action_permitted"] is True

    # 3. Verify overdraft proposal
    overdraft_payload = {
        "vdc": vdc_data,
        "proposed_action": "quote",
        "proposed_amount": 100000.0,
    }
    overdraft_resp = client.post("/api/v1/a2a/vdc/verify", json=overdraft_payload)
    assert overdraft_resp.status_code == 200
    assert overdraft_resp.json()["is_valid"] is False
    assert overdraft_resp.json()["amount_permitted"] is False


def test_negotiation_ledger_endpoints_full_cycle(client: TestClient) -> None:
    """Validate negotiation step append, ledger query, chain verification, and audit dossier export."""
    # Issue VDC for Peer 1
    p1_resp = client.post(
        "/api/v1/a2a/vdc/issue",
        json={
            "issuer_did": "did:corp:corp-one",
            "issuer_name": "Corp One Inc",
            "holder_agent_id": "agent-p1",
            "holder_name": "Agent P1",
            "max_transaction_amount": 50000.0,
            "allowed_actions": ["quote", "final_contract"],
            "issuer_public_key": "pubkey_p1",
        },
    )
    vdc1 = p1_resp.json()

    # Issue VDC for Peer 2
    p2_resp = client.post(
        "/api/v1/a2a/vdc/issue",
        json={
            "issuer_did": "did:corp:corp-two",
            "issuer_name": "Corp Two LLC",
            "holder_agent_id": "agent-p2",
            "holder_name": "Agent P2",
            "max_transaction_amount": 50000.0,
            "allowed_actions": ["quote", "final_contract"],
            "issuer_public_key": "pubkey_p2",
        },
    )
    vdc2 = p2_resp.json()

    session_id = "sess-commercial-x99"

    # Compute terms and signatures
    digest = NegotiationTerms.compute_digest(
        action="final_contract",
        item_description="Annual Dedicated Cloud Sandbox Instance Pool",
        quantity=1,
        unit_price=45000.0,
        total_amount=45000.0,
        currency="USD",
        delivery_deadline="2026-12-31",
    )
    sig1 = A2ANegotiationLedgerService.sign_terms_digest("pubkey_p1", digest)
    sig2 = A2ANegotiationLedgerService.sign_terms_digest("pubkey_p2", digest)

    step_payload = {
        "session_id": session_id,
        "initiator_agent_id": "agent-p1",
        "responder_agent_id": "agent-p2",
        "initiator_vdc": vdc1,
        "responder_vdc": vdc2,
        "terms": {
            "terms_id": "term-contract-01",
            "action": "final_contract",
            "item_description": "Annual Dedicated Cloud Sandbox Instance Pool",
            "quantity": 1,
            "unit_price": 45000.0,
            "total_amount": 45000.0,
            "currency": "USD",
            "delivery_deadline": "2026-12-31",
            "terms_digest": digest,
        },
        "initiator_signature": sig1,
        "responder_signature": sig2,
    }

    # 1. POST negotiation step
    step_resp = client.post("/api/v1/a2a/vdc/negotiation/step", json=step_payload)
    assert step_resp.status_code == 200
    block_data = step_resp.json()
    assert block_data["session_id"] == session_id
    assert block_data["step_index"] == 0
    assert block_data["block_hash"] != ""

    # 2. GET ledger blocks
    ledger_resp = client.get(f"/api/v1/a2a/vdc/negotiation/{session_id}/ledger")
    assert ledger_resp.status_code == 200
    assert len(ledger_resp.json()) == 1

    # 3. GET verify chain
    verify_resp = client.get(
        f"/api/v1/a2a/vdc/negotiation/{session_id}/verify?initiator_public_key=pubkey_p1&responder_public_key=pubkey_p2"
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["chain_intact"] is True

    # 4. GET export dossier
    export_resp = client.get(
        f"/api/v1/a2a/vdc/negotiation/{session_id}/export-dossier"
        f"?initiator_did=did:corp:corp-one&responder_did=did:corp:corp-two"
        f"&initiator_public_key=pubkey_p1&responder_public_key=pubkey_p2"
    )
    assert export_resp.status_code == 200
    dossier = export_resp.json()
    assert dossier["chain_intact"] is True
    assert dossier["final_contract_agreed"] is True
    assert len(dossier["blocks"]) == 1
