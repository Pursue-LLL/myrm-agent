"""API endpoint tests for localhost anti-DNS-rebinding and origin anti-hijack guard."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.localhost_anti_hijack_router import (
    router as localhost_anti_hijack_router,
)
from app.services.security.localhost_anti_hijack_service import (
    LocalhostAntiHijackService,
    get_localhost_anti_hijack_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = LocalhostAntiHijackService(
        cookie_name="myrm_local_session",
        cookie_max_age=3600,
    )
    app = FastAPI()
    app.include_router(localhost_anti_hijack_router, prefix="/api/v1/security")
    app.dependency_overrides[get_localhost_anti_hijack_service] = lambda: test_service
    return TestClient(app)


def test_generate_and_exchange_token_endpoint(client: TestClient) -> None:
    """Test generating a setup token and exchanging it for an HttpOnly session cookie."""
    # 1. Generate token
    gen_resp = client.post(
        "/api/v1/security/anti-hijack/generate-token",
        params={"ttl_seconds": 60, "client_binding": "tauri-desktop"},
    )
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    token = gen_data["token"]
    assert token is not None
    assert gen_data["ttl_seconds"] == 60

    # 2. Exchange token
    ex_resp = client.post(
        "/api/v1/security/anti-hijack/exchange-token",
        json={"token": token, "client_identifier": "tauri-desktop"},
    )
    assert ex_resp.status_code == 200
    ex_data = ex_resp.json()
    assert ex_data["success"] is True
    session_id = ex_data["session_id"]
    assert session_id is not None

    # Check Set-Cookie in response headers
    set_cookie_header = ex_resp.headers.get("set-cookie")
    assert set_cookie_header is not None
    assert "myrm_local_session" in set_cookie_header
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=strict" in set_cookie_header.lower()

    # 3. Duplicate exchange must be rejected with 400
    dup_resp = client.post(
        "/api/v1/security/anti-hijack/exchange-token",
        json={"token": token, "client_identifier": "tauri-desktop"},
    )
    assert dup_resp.status_code == 400
    assert "already been consumed" in dup_resp.json()["detail"]


def test_exchange_invalid_token(client: TestClient) -> None:
    """Test exchanging an unknown token returns 400."""
    resp = client.post(
        "/api/v1/security/anti-hijack/exchange-token",
        json={"token": "non-existent-token-12345"},
    )
    assert resp.status_code == 400
    assert "Token not found" in resp.json()["detail"]


def test_verify_request_endpoint(client: TestClient) -> None:
    """Test verify-request endpoint validates Host, Origin, and Referer headers."""
    # 1. Valid local request
    valid_resp = client.post(
        "/api/v1/security/anti-hijack/verify-request",
        json={
            "host": "localhost:8000",
            "origin": "http://localhost:5173",
            "referer": "http://localhost:5173/chat",
            "client_ip": "127.0.0.1",
        },
    )
    assert valid_resp.status_code == 200
    valid_data = valid_resp.json()
    assert valid_data["is_allowed"] is True
    assert valid_data["status"] == "allowed"

    # 2. DNS rebinding host spoofing attack
    rebinding_resp = client.post(
        "/api/v1/security/anti-hijack/verify-request",
        json={
            "host": "attacker-dns-rebinding.com:8000",
            "origin": "http://localhost:8000",
            "client_ip": "127.0.0.1",
        },
    )
    assert rebinding_resp.status_code == 200
    rebinding_data = rebinding_resp.json()
    assert rebinding_data["is_allowed"] is False
    assert rebinding_data["status"] == "rejected_host"

    # 3. Malicious Origin cross-site attempt
    origin_resp = client.post(
        "/api/v1/security/anti-hijack/verify-request",
        json={
            "host": "127.0.0.1:8000",
            "origin": "https://malicious-tracker.xyz",
            "client_ip": "127.0.0.1",
        },
    )
    assert origin_resp.status_code == 200
    origin_data = origin_resp.json()
    assert origin_data["is_allowed"] is False
    assert origin_data["status"] == "rejected_origin"


def test_get_policy_endpoint(client: TestClient) -> None:
    """Test policy endpoint returns current whitelist rules."""
    resp = client.get("/api/v1/security/anti-hijack/policy")
    assert resp.status_code == 200
    data = resp.json()
    assert "127.0.0.1" in data["allowed_hosts"]
    assert "localhost" in data["allowed_hosts"]
    assert data["enforce_strict_mode"] is True


def test_revoke_session_endpoint(client: TestClient) -> None:
    """Test revoking an active session deletes cookie."""
    # First generate and exchange
    gen_resp = client.post(
        "/api/v1/security/anti-hijack/generate-token",
        params={"ttl_seconds": 60},
    )
    token = gen_resp.json()["token"]
    ex_resp = client.post(
        "/api/v1/security/anti-hijack/exchange-token",
        json={"token": token},
    )
    session_id = ex_resp.json()["session_id"]

    # Revoke
    rev_resp = client.post(
        "/api/v1/security/anti-hijack/revoke-session",
        json={"session_id": session_id},
    )
    assert rev_resp.status_code == 200
    rev_data = rev_resp.json()
    assert rev_data["success"] is True

    # Revoke again returns False
    rev_dup = client.post(
        "/api/v1/security/anti-hijack/revoke-session",
        json={"session_id": session_id},
    )
    assert rev_dup.status_code == 200
    assert rev_dup.json()["success"] is False
