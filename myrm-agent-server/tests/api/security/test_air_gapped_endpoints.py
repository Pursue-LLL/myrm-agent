"""Integration tests for Air-Gapped Sovereign Intelligence API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.air_gapped_router import router as air_gapped_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting air_gapped_router."""
    test_app = FastAPI(title="Air-Gapped Sovereign Test App")
    test_app.include_router(air_gapped_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_air_gapped_status_and_tier_endpoints(client: TestClient) -> None:
    # 1. Get initial status
    resp = client.get("/api/v1/security/air-gapped/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_tier" in data
    assert "is_air_gapped" in data

    # 2. Update tier
    update_resp = client.post(
        "/api/v1/security/air-gapped/tier",
        json={"tier": "conservative"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["current_tier"] == "conservative"
    assert update_resp.json()["is_air_gapped"] is False

    # Switch back to air_gapped_sovereign
    reset_resp = client.post(
        "/api/v1/security/air-gapped/tier",
        json={"tier": "air_gapped_sovereign"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["current_tier"] == "air_gapped_sovereign"
    assert reset_resp.json()["is_air_gapped"] is True


def test_assert_zero_egress_and_compliance_dossier_endpoints(client: TestClient) -> None:
    # 1. Trigger cryptographic assertion
    assert_resp = client.post("/api/v1/security/air-gapped/assert-zero-egress")
    assert assert_resp.status_code == 200
    assert_data = assert_resp.json()
    assert "assertion_hash" in assert_data
    assert "is_zero_egress_compliant" in assert_data
    assert len(assert_data["assertion_hash"]) == 64

    # 2. Get compliance dossier
    dossier_resp = client.get(
        "/api/v1/security/air-gapped/compliance-dossier?organization_id=fintech_corp_china"
    )
    assert dossier_resp.status_code == 200
    dossier = dossier_resp.json()
    assert dossier["organization_id"] == "fintech_corp_china"
    assert "GB/T" in dossier["compliance_standard"]
    assert len(dossier["sha256_dossier_signature"]) == 64
    assert dossier["encryption_at_rest_enabled"] is True

    # 3. List attempts
    attempts_resp = client.get("/api/v1/security/air-gapped/attempts?limit=50")
    assert attempts_resp.status_code == 200
    assert isinstance(attempts_resp.json(), list)
