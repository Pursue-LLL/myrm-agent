"""API endpoint tests for Agent Lifecycle Digital Certificate and Emergency Revocation Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.agent_lifecycle_certificate_router import (
    router as agent_lifecycle_certificate_router,
)
from app.services.security.agent_lifecycle_certificate_service import (
    AgentLifecycleCertificateService,
    get_agent_lifecycle_certificate_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = AgentLifecycleCertificateService()
    app = FastAPI()
    app.include_router(agent_lifecycle_certificate_router)
    app.dependency_overrides[get_agent_lifecycle_certificate_service] = lambda: test_service
    return TestClient(app)


def test_mint_agent_certificate_endpoint(client: TestClient) -> None:
    """Test POST /agent-certs/mint creates and signs certificate."""
    payload = {
        "agent_id": "agent-procurement-001",
        "subject_dn": "CN=Procurement Agent, O=Enterprise, C=CN",
        "validity_days": 180,
        "attributes": {"dept": "supply-chain"},
    }
    response = client.post("/agent-certs/mint", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == "agent-procurement-001"
    assert data["status"] == "ACTIVE"
    assert data["cert_id"].startswith("cert-")
    assert len(data["signature_hex"]) == 64
    assert len(data["fingerprint_sha256"]) == 64


def test_verify_preflight_endpoint(client: TestClient) -> None:
    """Test POST /agent-certs/verify-preflight checks execution validity."""
    # Mint cert
    mint_resp = client.post(
        "/agent-certs/mint",
        json={
            "agent_id": "agent-compliance-002",
            "subject_dn": "CN=Compliance Agent, O=Legal, C=CN",
            "validity_days": 365,
        },
    )
    cert_id = mint_resp.json()["cert_id"]

    # Verify
    verify_resp = client.post("/agent-certs/verify-preflight", json={"cert_id": cert_id})
    assert verify_resp.status_code == 200
    verdict = verify_resp.json()
    assert verdict["is_allowed"] is True
    assert verdict["status"] == "ACTIVE"
    assert verdict["signature_valid"] is True
    assert verdict["not_expired"] is True
    assert verdict["not_revoked"] is True
    assert verdict["issuer_trusted"] is True


def test_emergency_revoke_and_crl_endpoints(client: TestClient) -> None:
    """Test POST /agent-certs/revoke and GET /agent-certs/crl/snapshot."""
    mint_resp = client.post(
        "/agent-certs/mint",
        json={
            "agent_id": "agent-compromised-003",
            "subject_dn": "CN=Hacked Agent, O=Test, C=CN",
            "validity_days": 30,
        },
    )
    cert_id = mint_resp.json()["cert_id"]

    # Revoke
    revoke_resp = client.post(
        "/agent-certs/revoke",
        json={
            "cert_id": cert_id,
            "reason": "MALICIOUS_BACKDOOR_DETECTED",
            "revoked_by": "soc-officer-dan",
        },
    )
    assert revoke_resp.status_code == 200
    rev_data = revoke_resp.json()
    assert rev_data["cert_id"] == cert_id
    assert rev_data["reason"] == "MALICIOUS_BACKDOOR_DETECTED"

    # Preflight now blocked
    verify_resp = client.post("/agent-certs/verify-preflight", json={"cert_id": cert_id})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_allowed"] is False
    assert verify_resp.json()["status"] == "REVOKED"

    # Check CRL snapshot
    crl_resp = client.get("/agent-certs/crl/snapshot")
    assert crl_resp.status_code == 200
    crl_data = crl_resp.json()
    assert crl_data["total_revoked"] >= 1


def test_get_certificate_and_health_dashboard_endpoints(client: TestClient) -> None:
    """Test GET /agent-certs/{cert_id} and GET /agent-certs/health/dashboard."""
    mint_resp = client.post(
        "/agent-certs/mint",
        json={
            "agent_id": "agent-health-004",
            "subject_dn": "CN=Health Agent, O=Dev, C=CN",
            "validity_days": 60,
        },
    )
    cert_id = mint_resp.json()["cert_id"]

    # Fetch cert
    get_resp = client.get(f"/agent-certs/{cert_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["cert_id"] == cert_id

    # Fetch dashboard
    dashboard_resp = client.get("/agent-certs/health/dashboard")
    assert dashboard_resp.status_code == 200
    dashboard_data = dashboard_resp.json()
    assert dashboard_data["total_certificates"] >= 1
    assert "healthy_count" in dashboard_data


def test_get_certificate_not_found(client: TestClient) -> None:
    """Test 404 on nonexistent cert."""
    resp = client.get("/agent-certs/cert-not-exists-999")
    assert resp.status_code == 404
