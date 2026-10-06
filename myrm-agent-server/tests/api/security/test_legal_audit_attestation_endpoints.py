"""API endpoint tests for Legal-Grade Cryptographic Audit Evidence and TSA Attestation Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.legal_audit_attestation_router import (
    router as legal_audit_attestation_router,
)
from app.services.security.legal_audit_attestation_service import (
    LegalAuditAttestationService,
    get_legal_audit_attestation_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = LegalAuditAttestationService()
    app = FastAPI()
    app.include_router(legal_audit_attestation_router)
    app.dependency_overrides[get_legal_audit_attestation_service] = lambda: test_service
    return TestClient(app)


def test_record_audit_entry_endpoint(client: TestClient) -> None:
    """Test POST /legal-audit/entries creates leaf node."""
    payload = {
        "session_id": "sess-contract-001",
        "actor_id": "usr-ceo-bob",
        "agent_cert_id": "cert-procurement-agent-v1",
        "action_name": "approve_purchase_order",
        "input_payload": {"po_id": "PO-9999", "amount": "850000"},
        "output_payload": {"status": "authorized"},
        "metadata": {"ip": "10.0.1.2"},
    }
    response = client.post("/legal-audit/entries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["leaf_index"] == 0
    assert len(data["leaf_hash"]) == 64
    assert data["entry_id"].startswith("ent-")


def test_anchor_tsa_endpoint(client: TestClient) -> None:
    """Test POST /legal-audit/tsa-anchor issues RFC 3161 token."""
    # First record an entry
    client.post(
        "/legal-audit/entries",
        json={
            "session_id": "sess-1",
            "actor_id": "usr-1",
            "agent_cert_id": "cert-1",
            "action_name": "db_write",
            "input_payload": {"table": "contracts"},
            "output_payload": {"rows": "1"},
            "metadata": {},
        },
    )

    response = client.post("/legal-audit/tsa-anchor", json={"algorithm": "SHA-256"})
    assert response.status_code == 200
    data = response.json()
    assert data["authority_id"] == "CN-GUIZHOU-CA-TSA-01"
    assert len(data["signature_hex"]) == 64
    assert len(data["digest"]) == 64


def test_pack_and_verify_evidence_dossier_endpoint(client: TestClient) -> None:
    """Test pack and verify endpoints for legal anti-repudiation dossier."""
    # Record entry
    entry_resp = client.post(
        "/legal-audit/entries",
        json={
            "session_id": "sess-arbitration-002",
            "actor_id": "usr-cto-carol",
            "agent_cert_id": "cert-deploy-agent-v2",
            "action_name": "deploy_prod_release",
            "input_payload": {"version": "v2.5.0"},
            "output_payload": {"exit_code": "0"},
            "metadata": {"git_commit": "abc1234"},
        },
    )
    entry_id = entry_resp.json()["entry_id"]

    # Pack dossier
    pack_resp = client.post(
        "/legal-audit/dossiers/pack",
        json={
            "entry_id": entry_id,
            "approver_id": "usr-board-member",
            "metadata": {"audit_reason": "annual_sox_review"},
        },
    )
    assert pack_resp.status_code == 201
    dossier = pack_resp.json()
    assert dossier["approver_id"] == "usr-board-member"
    assert dossier["entry_id"] == entry_id
    assert dossier["merkle_proof"]["is_valid"] is True

    # Verify dossier
    verify_resp = client.post("/legal-audit/dossiers/verify", json={"dossier": dossier})
    assert verify_resp.status_code == 200
    verdict = verify_resp.json()
    assert verdict["is_valid"] is True
    assert verdict["status"] == "VALID"
    assert verdict["leaf_match"] is True
    assert verdict["root_match"] is True
    assert verdict["tsa_match"] is True
    assert verdict["signature_match"] is True


def test_pack_nonexistent_dossier_returns_404(client: TestClient) -> None:
    """Test packing nonexistent entry returns HTTP 404."""
    response = client.post(
        "/legal-audit/dossiers/pack",
        json={"entry_id": "ent-missing-999"},
    )
    assert response.status_code == 404


def test_get_ledger_status_and_metrics_endpoints(client: TestClient) -> None:
    """Test GET /legal-audit/ledger/status and GET /legal-audit/metrics endpoints."""
    # Status
    status_resp = client.get("/legal-audit/ledger/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "total_entries" in status_data
    assert "root_hash" in status_data

    # Metrics
    metrics_resp = client.get("/legal-audit/metrics")
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert metrics_data["total_entries"] >= 0
    assert "total_dossiers_packed" in metrics_data
