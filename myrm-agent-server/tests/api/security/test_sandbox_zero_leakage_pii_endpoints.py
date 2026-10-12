"""API endpoint tests for Physical Sandbox Zero-Leakage Attestation and PII Firewall Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.sandbox_zero_leakage_pii_router import (
    router as sandbox_zero_leakage_pii_router,
)
from app.services.security.sandbox_zero_leakage_pii_service import (
    SandboxZeroLeakagePiiService,
    get_sandbox_zero_leakage_pii_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = SandboxZeroLeakagePiiService()
    app = FastAPI()
    app.include_router(sandbox_zero_leakage_pii_router)
    app.dependency_overrides[get_sandbox_zero_leakage_pii_service] = lambda: test_service
    return TestClient(app)


def test_attestation_issue_and_verify_endpoints(client: TestClient) -> None:
    # 1. Issue proof
    issue_resp = client.post(
        "/sandbox-zero-leakage/attestation/issue",
        json={
            "tenant_id": "tenant-api-test-1",
            "container_id": "container-xyz-123",
            "dedicated_volume_path": "/var/data/u1",
            "dedicated_database_lock": "lock-exclusive-456",
        },
    )
    assert issue_resp.status_code == 200
    proof = issue_resp.json()
    assert proof["tenant_id"] == "tenant-api-test-1"
    assert "attestation_signature" in proof

    # 2. Verify proof
    verify_resp = client.post(
        "/sandbox-zero-leakage/attestation/verify",
        json={"proof": proof},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_valid"] is True


def test_pii_scan_and_redact_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/sandbox-zero-leakage/pii/scan-redact",
        json={"text": "Please note that my son Lucas has asthma. Call 138-0013-8000."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["contains_child_privacy_violation"] is True
    assert "Lucas" not in data["sanitized_text"]
    assert "[CHILD_NAME_REDACTED]" in data["sanitized_text"]
    assert "[PHONE_REDACTED]" in data["sanitized_text"]


def test_transparency_audit_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/sandbox-zero-leakage/transparency/audit",
        json={
            "operator_name": "Myrm Official",
            "base_model_id": "meta-llama/Llama-3.1-70B",
            "data_jurisdiction": "local",
            "is_codebase_public": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "VERIFIED_TRANSPARENT"
    assert data["overall_score"] >= 0.85


def test_profile_sign_and_verify_endpoints(client: TestClient) -> None:
    sys_prompt = "You are an immutable helpful assistant."

    # 1. Sign profile
    sign_resp = client.post(
        "/sandbox-zero-leakage/profile/sign",
        json={
            "profile_id": "official-assistant-v1",
            "author": "Myrmidon",
            "model_id": "Llama-3.1",
            "system_prompt": sys_prompt,
            "is_official": True,
        },
    )
    assert sign_resp.status_code == 200
    profile = sign_resp.json()
    assert profile["is_official_verified"] is True

    # 2. Verify authentic profile
    v_resp = client.post(
        "/sandbox-zero-leakage/profile/verify",
        json={
            "profile": profile,
            "actual_system_prompt": sys_prompt,
        },
    )
    assert v_resp.status_code == 200
    assert v_resp.json()["is_valid"] is True
