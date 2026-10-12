"""API endpoint tests for Vetted Plugin Registry Trust Chain and Dynamic Capability Attestation Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.plugin_trust_attestation_router import (
    router as plugin_trust_attestation_router,
)
from app.services.security.plugin_trust_attestation_service import (
    PluginTrustAttestationService,
    get_plugin_trust_attestation_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = PluginTrustAttestationService()
    app = FastAPI()
    app.include_router(plugin_trust_attestation_router)
    app.dependency_overrides[get_plugin_trust_attestation_service] = lambda: test_service
    return TestClient(app)


def test_compute_digest_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/plugin-trust/compute-digest",
        json={"main.py": "print('hello')", "plugin.json": "{}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "digest" in data
    assert len(data["digest"]) == 64


def test_sign_and_verify_package_endpoints(client: TestClient) -> None:
    sign_resp = client.post(
        "/plugin-trust/sign",
        json={
            "plugin_id": "org.myrm.sandbox",
            "version": "1.0.0",
            "payload_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "trust_tier": "OFFICIAL_VERIFIED",
        },
    )
    assert sign_resp.status_code == 200
    package = sign_resp.json()
    assert package["plugin_id"] == "org.myrm.sandbox"
    assert package["trust_tier"] == "OFFICIAL_VERIFIED"
    assert "signature" in package

    # Verify matching payload
    verify_resp = client.post(
        "/plugin-trust/verify",
        json={
            "package": package,
            "actual_payload_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        },
    )
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["is_valid"] is True
    assert v_data["trust_tier"] == "OFFICIAL_VERIFIED"
    assert v_data["error_message"] is None

    # Verify tampered payload
    tampered_resp = client.post(
        "/plugin-trust/verify",
        json={
            "package": package,
            "actual_payload_sha256": "tampered_hash_123456",
        },
    )
    assert tampered_resp.status_code == 200
    t_data = tampered_resp.json()
    assert t_data["is_valid"] is False
    assert "mismatch" in t_data["error_message"]


def test_tokens_and_validate_operation_endpoints(client: TestClient) -> None:
    token_resp = client.post(
        "/plugin-trust/tokens",
        json={
            "plugin_id": "org.myrm.github",
            "version": "1.0.0",
            "network_domains": ["api.github.com"],
            "file_access_scope": "WORKSPACE_ONLY",
            "allow_shell_exec": False,
            "validity_seconds": 600,
        },
    )
    assert token_resp.status_code == 200
    token = token_resp.json()
    assert token["plugin_id"] == "org.myrm.github"
    assert "api.github.com" in token["granted_domains"]
    assert token["allow_shell"] is False

    # Validate authorized operation
    valid_op_resp = client.post(
        "/plugin-trust/validate-operation",
        json={
            "token": token,
            "target_domain": "api.github.com",
            "requires_shell": False,
        },
    )
    assert valid_op_resp.status_code == 200
    assert valid_op_resp.json()["allowed"] is True

    # Validate unauthorized outbound domain
    invalid_op_resp = client.post(
        "/plugin-trust/validate-operation",
        json={
            "token": token,
            "target_domain": "evil.hacker.com",
            "requires_shell": False,
        },
    )
    assert invalid_op_resp.status_code == 200
    assert invalid_op_resp.json()["allowed"] is False
