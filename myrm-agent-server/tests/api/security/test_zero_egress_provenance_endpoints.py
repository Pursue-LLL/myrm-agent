"""Integration tests for Enterprise Zero-Egress Audit Ledger & Asset Provenance API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.zero_egress_provenance_router import (
    router as zero_egress_provenance_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting zero_egress_provenance_router."""
    test_app = FastAPI(title="Zero-Egress Provenance Test App")
    test_app.include_router(zero_egress_provenance_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_audit_ledger_endpoints(client: TestClient) -> None:
    # 1. Record event
    record_payload = {
        "actor": "security-daemon",
        "action_type": "TOOL_INVOKE",
        "resource_target": "sandbox_exec",
        "input_payload": "ls -la",
        "output_payload": "total 0",
        "boundary_state": "SANDBOX_CONFINED",
    }
    resp = client.post("/api/v1/security/zero-egress-provenance/audit/record", json=record_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "TOOL_INVOKE"
    assert data["boundary_state"] == "SANDBOX_CONFINED"
    assert len(data["current_record_hash"]) == 64

    # 2. Verify ledger
    verify_resp = client.get("/api/v1/security/zero-egress-provenance/audit/verify")
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["is_intact"] is True
    assert v_data["total_records"] >= 1

    # 3. Export ledger
    export_resp = client.get("/api/v1/security/zero-egress-provenance/audit/export")
    assert export_resp.status_code == 200
    records = export_resp.json()
    assert len(records) >= 1
    assert any(r["record_id"] == data["record_id"] for r in records)


def test_certificate_and_provenance_endpoints(client: TestClient) -> None:
    # 1. Generate zero-egress certificate
    cert_payload = {
        "session_id": "sess-test-cert",
        "tenant_id": "tenant-test",
        "sandbox_id": "sbx-test",
        "attestation_level": "HIPAA_SOC2_CERTIFIED",
    }
    cert_resp = client.post(
        "/api/v1/security/zero-egress-provenance/certificate/generate", json=cert_payload
    )
    assert cert_resp.status_code == 200
    cert_data = cert_resp.json()
    assert cert_data["zero_data_retention_guaranteed"] is True
    assert cert_data["attestation_level"] == "HIPAA_SOC2_CERTIFIED"
    assert len(cert_data["signature"]) == 64

    # 2. Create asset provenance dossier
    prov_payload = {
        "asset_id": "asset-sql-query",
        "asset_name": "query.sql",
        "media_type": "text/x-sql",
        "content": "SELECT * FROM sales;",
        "session_id": "sess-test-cert",
        "prompt_text": "Extract sales table",
        "foundation_model_id": "gpt-4o",
        "license_type": "PROPRIETARY_WORK_FOR_HIRE",
        "ip_tier": "ENTERPRISE_INDEMNIFIED",
    }
    prov_resp = client.post(
        "/api/v1/security/zero-egress-provenance/provenance/create", json=prov_payload
    )
    assert prov_resp.status_code == 200
    dossier = prov_resp.json()
    assert dossier["asset_id"] == "asset-sql-query"
    assert dossier["ip_tier"] == "ENTERPRISE_INDEMNIFIED"

    # 3. Verify provenance match
    verify_payload = {
        "dossier": dossier,
        "content": "SELECT * FROM sales;",
    }
    v_resp = client.post(
        "/api/v1/security/zero-egress-provenance/provenance/verify", json=verify_payload
    )
    assert v_resp.status_code == 200
    assert v_resp.json()["is_verified"] is True

    # 4. Verify provenance mismatch
    verify_mismatch_payload = {
        "dossier": dossier,
        "content": "SELECT * FROM sales WHERE unauthorized=1;",
    }
    v_bad = client.post(
        "/api/v1/security/zero-egress-provenance/provenance/verify",
        json=verify_mismatch_payload,
    )
    assert v_bad.status_code == 200
    assert v_bad.json()["is_verified"] is False
