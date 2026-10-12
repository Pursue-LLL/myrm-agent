"""API endpoint tests for Secretless Credential Egress Proxy and Placeholder Swap Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.secretless_egress_proxy_router import (
    router as secretless_egress_proxy_router,
)
from app.services.security.secretless_egress_proxy_service import (
    SecretlessEgressProxyService,
    get_secretless_egress_proxy_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = SecretlessEgressProxyService()
    app = FastAPI()
    app.include_router(secretless_egress_proxy_router)
    app.dependency_overrides[get_secretless_egress_proxy_service] = lambda: test_service
    return TestClient(app)


def test_register_and_list_credentials_endpoints(client: TestClient) -> None:
    # 1. Register bound credential
    resp_reg = client.post(
        "/security/secretless-egress/register",
        json={
            "target_host": "api.github.com",
            "real_secret": "ghp_secure_prod_token_999",
            "auth_header_name": "Authorization",
            "auth_header_template": "Bearer {secret}",
        },
    )
    assert resp_reg.status_code == 200
    data = resp_reg.json()
    assert data["target_host"] == "api.github.com"
    assert data["placeholder"].startswith("myrm_cred_")
    assert data["is_active"] is True

    # 2. List credentials
    resp_list = client.get("/security/secretless-egress/credentials")
    assert resp_list.status_code == 200
    creds = resp_list.json()
    assert len(creds) == 1
    assert creds[0]["target_host"] == "api.github.com"


def test_inspect_and_swap_authorized_endpoint(client: TestClient) -> None:
    # Register credential
    resp_reg = client.post(
        "/security/secretless-egress/register",
        json={
            "target_host": "api.github.com",
            "real_secret": "ghp_secure_prod_token_999",
        },
    )
    assert resp_reg.status_code == 200
    placeholder = resp_reg.json()["placeholder"]

    # Inspect outbound request using placeholder
    resp_swap = client.post(
        "/security/secretless-egress/inspect-swap",
        json={
            "target_host": "api.github.com",
            "path": "/repos/org/repo",
            "method": "GET",
            "headers": {"Authorization": f"Bearer {placeholder}"},
        },
    )
    assert resp_swap.status_code == 200
    swap_data = resp_swap.json()
    assert swap_data["is_allowed"] is True
    assert swap_data["status_code"] == 200
    assert (
        swap_data["headers_to_inject"]["Authorization"]
        == "Bearer ghp_secure_prod_token_999"
    )
    assert swap_data["event"]["is_swapped"] is True


def test_inspect_and_swap_cross_domain_blocked_endpoint(client: TestClient) -> None:
    # Register credential for api.github.com
    resp_reg = client.post(
        "/security/secretless-egress/register",
        json={
            "target_host": "api.github.com",
            "real_secret": "ghp_secure_prod_token_999",
        },
    )
    assert resp_reg.status_code == 200
    placeholder = resp_reg.json()["placeholder"]

    # Exfiltration attempt to untrusted domain
    resp_leak = client.post(
        "/security/secretless-egress/inspect-swap",
        json={
            "target_host": "attacker-controlled.site",
            "path": "/collect-creds",
            "method": "POST",
            "headers": {"Authorization": f"Bearer {placeholder}"},
        },
    )
    assert resp_leak.status_code == 200
    leak_data = resp_leak.json()
    assert leak_data["is_allowed"] is False
    assert leak_data["status_code"] == 403
    assert "Cross-domain exfiltration blocked" in leak_data["event"]["block_reason"]


def test_revoke_and_audit_events_endpoints(client: TestClient) -> None:
    # Register
    client.post(
        "/security/secretless-egress/register",
        json={
            "target_host": "api.slack.com",
            "real_secret": "xoxb-slack-secret-999",
        },
    )

    # Revoke
    resp_revoke = client.post(
        "/security/secretless-egress/revoke",
        json={"target_host": "api.slack.com"},
    )
    assert resp_revoke.status_code == 200
    assert resp_revoke.json()["success"] is True

    # Audit events
    resp_events = client.get("/security/secretless-egress/events?limit=20")
    assert resp_events.status_code == 200
    events = resp_events.json()
    assert isinstance(events, list)
