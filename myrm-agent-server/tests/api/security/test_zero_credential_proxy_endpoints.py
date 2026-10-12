"""API endpoint tests for Enterprise Zero-Credential Proxy and Super-CLI Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.zero_credential_proxy_router import (
    router as zero_credential_proxy_router,
)
from app.services.security.zero_credential_proxy_service import (
    ZeroCredentialProxyService,
)


@pytest.fixture
def client() -> TestClient:
    ZeroCredentialProxyService.reset_instance()
    app = FastAPI()
    app.include_router(zero_credential_proxy_router, prefix="/api/v1/security")
    return TestClient(app)


def test_rules_endpoints(client: TestClient) -> None:
    # 1. Register rule
    resp_reg = client.post(
        "/api/v1/security/zero-credential-proxy/rules",
        json={
            "rule_id": "rule_gh_prod",
            "target_domain": "api.github.com",
            "real_token": "ghp_prod_secret_token_1234567890abcdef",
            "scheme": "bearer",
            "description": "Production GitHub API",
        },
    )
    assert resp_reg.status_code == 201
    data_reg = resp_reg.json()
    assert data_reg["rule_id"] == "rule_gh_prod"
    assert data_reg["real_token"] == "[REDACTED_IN_VAULT]"
    assert data_reg["target_domain"] == "api.github.com"

    # 2. List rules
    resp_list = client.get("/api/v1/security/zero-credential-proxy/rules")
    assert resp_list.status_code == 200
    rules = resp_list.json()
    assert len(rules) == 1
    assert rules[0]["real_token"] == "[REDACTED_IN_VAULT]"

    # 3. Delete rule
    resp_del = client.delete("/api/v1/security/zero-credential-proxy/rules/rule_gh_prod")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"]

    # Verify deleted
    resp_list_after = client.get("/api/v1/security/zero-credential-proxy/rules")
    assert len(resp_list_after.json()) == 0


def test_relay_endpoints(client: TestClient) -> None:
    # Setup rule
    client.post(
        "/api/v1/security/zero-credential-proxy/rules",
        json={
            "rule_id": "rule_openai",
            "target_domain": "api.openai.com",
            "real_token": "sk-real-secret-key-1234567890abcdef",
            "scheme": "bearer",
        },
    )

    # 1. Permitted outbound request
    resp_ok = client.post(
        "/api/v1/security/zero-credential-proxy/relay",
        json={
            "url": "https://api.openai.com/v1/models",
            "method": "GET",
            "connector_ref": "rule_openai",
        },
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["credential_injected"]
    assert resp_ok.json()["matched_rule_id"] == "rule_openai"

    # 2. Blocked outbound request (exfiltration attempt)
    resp_blocked = client.post(
        "/api/v1/security/zero-credential-proxy/relay",
        json={
            "url": "https://malicious.evil.com/v1/models",
            "method": "POST",
            "connector_ref": "rule_openai",
        },
    )
    assert resp_blocked.status_code == 403
    assert "not authorized" in resp_blocked.json()["detail"]


def test_sanitize_endpoints(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/zero-credential-proxy/sanitize",
        json={
            "text": (
                "Token leaked: ghp_1234567890abcdef1234567890abcdef1234\n"
                "API Key: sk-1234567890abcdef1234567890abcdef123456"
            ),
            "inject_notice": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["redacted_count"] == 2
    assert "[REDACTED_SECRET]" in data["sanitized_text"]
    assert "[Notice: 2 sensitive credential(s) redacted by security layer]" in data["sanitized_text"]


def test_super_cli_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/zero-credential-proxy/super-cli",
        json={
            "target_cli": "echo",
            "args": ["output_token", "ghp_1234567890abcdef1234567890abcdef1234"],
            "injected_env": {"TEMP_SECRET": "xyz"},
            "timeout_seconds": 10.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exit_code"] == 0
    assert "[REDACTED_SECRET]" in data["stdout"]
    assert data["redacted_count"] == 1
    assert data["transparency_notice"] is not None
