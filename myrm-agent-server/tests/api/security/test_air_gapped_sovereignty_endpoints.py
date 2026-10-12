"""
[POS] tests/api/security/test_air_gapped_sovereignty_endpoints.py
[INPUT] app.api.security.air_gapped_sovereignty_router, app.services.security.air_gapped_sovereignty_service
[OUTPUT] endpoint tests

API endpoint tests for Air-Gapped Offline Trust Store & Sovereign Model Fallback Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.air_gapped_sovereignty_router import (
    router as air_gapped_sovereignty_router,
)
from app.services.security.air_gapped_sovereignty_service import (
    AirGappedSovereigntyService,
    get_air_gapped_sovereignty_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = AirGappedSovereigntyService()
    app = FastAPI()
    app.include_router(air_gapped_sovereignty_router)
    app.dependency_overrides[get_air_gapped_sovereignty_service] = lambda: test_service
    return TestClient(app)


def test_mode_endpoints(client: TestClient) -> None:
    """Test GET and PUT /air-gapped-sovereignty/mode."""
    get_res = client.get("/air-gapped-sovereignty/mode")
    assert get_res.status_code == 200
    assert get_res.json()["active_mode"] == "AIR_GAPPED_ISOLATED"

    put_res = client.put(
        "/air-gapped-sovereignty/mode",
        json={"mode": "ONLINE"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["active_mode"] == "ONLINE"

    get_res2 = client.get("/air-gapped-sovereignty/mode")
    assert get_res2.status_code == 200
    assert get_res2.json()["active_mode"] == "ONLINE"


def test_validate_cert_and_crl_endpoints(client: TestClient) -> None:
    """Test POST /air-gapped-sovereignty/validate-cert and /import-crl."""
    now = time.time()
    cert_req = {
        "cert_pem": "CERT-SOVEREIGN-CLIENT-001",
        "cert_serial": "SN-CLIENT-SOV-100",
        "issuer_ca": "GuizhouCA",
        "valid_until": now + 86400,
    }

    # 1. Validate legitimate certificate
    val_res = client.post("/air-gapped-sovereignty/validate-cert", json=cert_req)
    assert val_res.status_code == 200
    v_data = val_res.json()
    assert v_data["is_valid"] is True
    assert v_data["ca_name"] == "GuizhouCA"
    assert v_data["is_revoked"] is False
    assert len(v_data["fingerprint_sm3"]) == 64

    # 2. Import CRL revocation
    crl_res = client.post(
        "/air-gapped-sovereignty/import-crl",
        json={"revoked_serials": ["SN-CLIENT-SOV-100"]},
    )
    assert crl_res.status_code == 200
    assert crl_res.json()["imported_count"] == 1

    # 3. Validate revoked certificate
    rev_res = client.post("/air-gapped-sovereignty/validate-cert", json=cert_req)
    assert rev_res.status_code == 200
    r_data = rev_res.json()
    assert r_data["is_valid"] is False
    assert r_data["is_revoked"] is True


def test_resolve_model_endpoint(client: TestClient) -> None:
    """Test POST /air-gapped-sovereignty/resolve-model."""
    # System starts in AIR_GAPPED_ISOLATED
    res = client.post(
        "/air-gapped-sovereignty/resolve-model",
        json={"requested_model_id": "claude-3-opus", "is_remote_healthy": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["was_fallback"] is True
    assert data["effective_target"]["model_id"] == "qwen2.5-coder:32b"
    assert data["effective_target"]["is_local_sovereign"] is True
    assert data["active_mode"] == "AIR_GAPPED_ISOLATED"


def test_audit_bundle_endpoints(client: TestClient) -> None:
    """Test POST /air-gapped-sovereignty/pack-audit-bundle and /verify-audit-bundle."""
    records = [
        {"event": "AGENT_INIT", "agent_id": "agent-sov-1"},
        {"event": "SAFEGUARD_CHECK", "status": "PASSED"},
    ]

    pack_res = client.post(
        "/air-gapped-sovereignty/pack-audit-bundle",
        json={"records": records, "metadata": {"classification": "TOP_SECRET"}},
    )
    assert pack_res.status_code == 200
    bundle = pack_res.json()
    assert bundle["record_count"] == 2
    assert bundle["is_sealed"] is True
    assert len(bundle["sm3_root_digest"]) == 64

    # Verify matching bundle
    verify_res = client.post(
        "/air-gapped-sovereignty/verify-audit-bundle",
        json={"bundle": bundle, "raw_records": records},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["is_valid"] is True

    # Tampered records fail verification
    tampered_records = [records[0], {"event": "MALICIOUS_INJECTION", "status": "FAIL"}]
    verify_tampered = client.post(
        "/air-gapped-sovereignty/verify-audit-bundle",
        json={"bundle": bundle, "raw_records": tampered_records},
    )
    assert verify_tampered.status_code == 200
    assert verify_tampered.json()["is_valid"] is False


def test_hash_and_metrics_endpoints(client: TestClient) -> None:
    """Test POST /air-gapped-sovereignty/hash/sm3 and GET /metrics."""
    hash_res = client.post(
        "/air-gapped-sovereignty/hash/sm3",
        json={"data": "abc"},
    )
    assert hash_res.status_code == 200
    assert (
        hash_res.json()["sm3_digest"]
        == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    )

    metrics_res = client.get("/air-gapped-sovereignty/metrics")
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert "total_offline_validations" in m_data
    assert "audit_bundles_sealed" in m_data
