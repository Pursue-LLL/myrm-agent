"""
[POS] tests/api/security/test_code_signing_gate_endpoints.py
[INPUT] app.api.security.code_signing_gate_router, app.services.security.code_signing_gate_service
[OUTPUT] endpoint tests

API endpoint tests for Developer Identity Attestation & Agent Package Code Signing Gate Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.code_signing_gate import CodeSignatureVerifier

from app.api.security.code_signing_gate_router import (
    router as code_signing_gate_router,
)
from app.services.security.code_signing_gate_service import (
    CodeSigningGateService,
    get_code_signing_gate_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = CodeSigningGateService()
    app = FastAPI()
    app.include_router(code_signing_gate_router)
    app.dependency_overrides[get_code_signing_gate_service] = lambda: test_service
    return TestClient(app)


def test_sign_and_verify_endpoints(client: TestClient) -> None:
    """Test POST /code-signing/sign-package and POST /code-signing/verify-package."""
    priv_pem, pub_pem = CodeSignatureVerifier.generate_keypair()
    now = time.time()

    cert_payload = {
        "developer_id": "dev-api-01",
        "developer_name": "API Engineer",
        "org_dn": "CN=Dev,O=APIOrg,C=CN",
        "issuer_ca": "GuizhouCA",
        "cert_serial": "CERT-API-9999",
        "valid_until": now + 86400.0,
        "public_key_pem": pub_pem,
        "is_internal_enterprise": True,
    }

    files = {
        "SKILL.md": "# API Gateway Skill",
        "main.py": "def handle(): pass",
    }

    # 1. Sign package via REST
    sign_payload = {
        "package_id": "pkg-api-01",
        "package_name": "api-gateway-bot",
        "version": "1.0.0",
        "files": files,
        "private_key_pem": priv_pem,
        "cert_info": cert_payload,
    }
    sign_resp = client.post("/code-signing/sign-package", json=sign_payload)
    assert sign_resp.status_code == 200
    signed_pkg = sign_resp.json()
    assert signed_pkg["package_id"] == "pkg-api-01"
    assert len(signed_pkg["signature_b64"]) > 0
    assert len(signed_pkg["manifest_entries"]) == 2

    # 2. Verify legitimate package
    verify_resp = client.post(
        "/code-signing/verify-package",
        json={"package": signed_pkg, "actual_files": files},
    )
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["is_allowed"] is True
    assert v_data["verdict"] == "VERIFIED"
    assert v_data["verified_developer"] == "API Engineer"
    assert v_data["is_enterprise_verified"] is True

    # 3. Detect tampered file
    tampered_files = dict(files)
    tampered_files["main.py"] = "def handle(): inject_payload()"
    tampered_resp = client.post(
        "/code-signing/verify-package",
        json={"package": signed_pkg, "actual_files": tampered_files},
    )
    assert tampered_resp.status_code == 200
    t_data = tampered_resp.json()
    assert t_data["is_allowed"] is False
    assert t_data["verdict"] == "TAMPERED_MANIFEST_DIGEST"


def test_policy_and_revocation_endpoints(client: TestClient) -> None:
    """Test GET/PUT /code-signing/policy and POST /code-signing/revoke-cert."""
    # 1. Default policy
    get_resp = client.get("/code-signing/policy")
    assert get_resp.status_code == 200
    assert get_resp.json()["active_policy"] == "VERIFIED_CA_ONLY"

    # 2. Update policy
    put_resp = client.put(
        "/code-signing/policy",
        json={"policy": "STRICT_ENTERPRISE_ONLY"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["active_policy"] == "STRICT_ENTERPRISE_ONLY"

    # Verify updated
    get_resp2 = client.get("/code-signing/policy")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["active_policy"] == "STRICT_ENTERPRISE_ONLY"

    # 3. Revoke certificate
    revoke_resp = client.post(
        "/code-signing/revoke-cert",
        json={"cert_serial": "REVOKED-SN-001"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True


def test_metrics_endpoint(client: TestClient) -> None:
    """Test GET /code-signing/metrics."""
    resp = client.get("/code-signing/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_verifications" in data
    assert "verified_count" in data
    assert "tampered_count" in data
    assert "signature_failures" in data
