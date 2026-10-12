"""
[POS] tests/api/security/test_case_variant_scrubber_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.case_variant_scrubber_router, app.services.security.case_variant_scrubber_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for Case-Variant Credential Scrubbing & Declarative OAuth PKCE Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.case_variant_scrubber_router import router as scrubber_router
from app.services.security.case_variant_scrubber_service import (
    CaseVariantScrubberService,
    get_case_variant_scrubber_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = CaseVariantScrubberService()
    app = FastAPI()
    app.include_router(scrubber_router)
    app.dependency_overrides[get_case_variant_scrubber_service] = lambda: test_service
    return TestClient(app)


def test_scrub_env_and_injection_detection_endpoints(client: TestClient) -> None:
    """Validate POST /scrub-env and POST /detect-injections."""
    # 1. Scrub env
    scrub_res = client.post(
        "/case-variant-scrubber/scrub-env",
        json={
            "env_dict": {
                "Openai_Api_Key": "sk-12345",
                "github_Token": "ghp-67890",
                "SAFE_VAR": "safe_val",
            },
            "action": "DROP",
        },
    )
    assert scrub_res.status_code == 200
    s_data = scrub_res.json()
    assert s_data["total_dropped"] == 2
    assert "Openai_Api_Key" not in s_data["clean_env"]
    assert s_data["clean_env"]["SAFE_VAR"] == "safe_val"

    # 2. Detect injections
    detect_res = client.post(
        "/case-variant-scrubber/detect-injections",
        json={
            "env_dict": {
                "Openai_Api_Key": "sk-12345",
                "NORMAL_UPPERCASE": "value",
            }
        },
    )
    assert detect_res.status_code == 200
    d_data = detect_res.json()
    assert d_data["has_injection_risk"] is True
    assert "Openai_Api_Key" in d_data["suspicious_keys"]


def test_oauth_pkce_endpoints_lifecycle(client: TestClient) -> None:
    """Validate PKCE initiate, exchange, provider list, and registration endpoints."""
    # 1. List providers
    list_res = client.get("/case-variant-scrubber/providers")
    assert list_res.status_code == 200
    providers = list_res.json()
    assert len(providers) >= 2

    # 2. Register custom provider
    reg_res = client.post(
        "/case-variant-scrubber/providers",
        json={
            "provider_id": "test_provider_hub",
            "display_name": "Test Provider Hub",
            "authorization_endpoint": "https://hub.test/oauth/auth",
            "token_endpoint": "https://hub.test/oauth/token",
            "client_id": "client-abc",
            "scopes": ["inference"],
            "challenge_method": "S256",
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["provider"]["provider_id"] == "test_provider_hub"

    # 3. Initiate PKCE flow
    init_res = client.post(
        "/case-variant-scrubber/pkce/initiate",
        json={
            "provider_id": "test_provider_hub",
            "redirect_uri": "https://localhost:8000/oauth/callback",
            "ttl_seconds": 300.0,
        },
    )
    assert init_res.status_code == 200
    flow_data = init_res.json()
    flow_id = flow_data["flow_id"]
    state_token = flow_data["state_token"]
    assert flow_id.startswith("flow-")

    # 4. Exchange PKCE flow
    exchange_res = client.post(
        "/case-variant-scrubber/pkce/exchange",
        json={
            "flow_id": flow_id,
            "code": "auth_authorization_code_xyz",
            "state": state_token,
        },
    )
    assert exchange_res.status_code == 200
    ex_data = exchange_res.json()
    assert ex_data["code"] == "auth_authorization_code_xyz"
    assert ex_data["code_verifier"] != ""

    # 5. Metrics
    metrics_res = client.get("/case-variant-scrubber/metrics")
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert m_data["pkce_flows_initiated_total"] >= 1
    assert m_data["pkce_tokens_exchanged_total"] >= 1
