"""Integration tests for Desktop OAuth & RFC 8628 Device Code API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.desktop_oauth_device_router import (
    router as desktop_oauth_device_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting desktop_oauth_device_router."""
    test_app = FastAPI(title="Desktop OAuth Device Test App")
    test_app.include_router(desktop_oauth_device_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_init_desktop_oauth_endpoint(client: TestClient) -> None:
    payload = {
        "provider": "github",
        "client_id": "gh-desktop-app",
        "base_auth_url": "https://github.com/login/oauth/authorize",
        "scopes": ["read:user", "repo"],
        "loopback_port": 41920,
    }
    resp = client.post("/api/v1/security/desktop-oauth-device/init-desktop-oauth", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "github"
    assert "https://github.com/login/oauth/authorize?" in data["authorization_url"]
    assert "code_challenge=" in data["authorization_url"]
    assert "code_challenge_method=S256" in data["authorization_url"]
    assert len(data["code_verifier"]) > 40
    assert data["redirect_uri"] == "http://127.0.0.1:41920/callback"


def test_device_code_endpoints_lifecycle(client: TestClient) -> None:
    # 1. Initiate device flow
    init_payload = {
        "client_id": "headless-cli",
        "verification_uri": "https://auth.myrm.dev/device",
        "scope": "agent:run",
        "expires_in": 600,
        "interval": 2,
    }
    resp_init = client.post("/api/v1/security/desktop-oauth-device/device/initiate", json=init_payload)
    assert resp_init.status_code == 200
    init_data = resp_init.json()
    device_code = init_data["device_code"]
    user_code = init_data["user_code"]
    assert "-" in user_code
    assert init_data["status"] == "authorization_pending"

    # 2. Poll before authorization
    poll_payload = {"device_code": device_code, "enforce_interval": False}
    resp_poll_pending = client.post("/api/v1/security/desktop-oauth-device/device/poll", json=poll_payload)
    assert resp_poll_pending.status_code == 200
    poll_data_pending = resp_poll_pending.json()
    assert poll_data_pending["status"] == "authorization_pending"
    assert poll_data_pending["access_token"] is None

    # 3. Authorize via user code
    auth_payload = {
        "user_code": user_code,
        "access_token": "act_live_device_token_xyz",
        "refresh_token": "rft_live_device_token_xyz",
        "expires_in": 3600,
    }
    resp_auth = client.post("/api/v1/security/desktop-oauth-device/device/authorize", json=auth_payload)
    assert resp_auth.status_code == 200
    assert resp_auth.json()["success"] is True

    # 4. Poll after authorization
    resp_poll_authed = client.post("/api/v1/security/desktop-oauth-device/device/poll", json=poll_payload)
    assert resp_poll_authed.status_code == 200
    poll_data_authed = resp_poll_authed.json()
    assert poll_data_authed["status"] == "authorized"
    assert poll_data_authed["access_token"] == "act_live_device_token_xyz"
    assert poll_data_authed["refresh_token"] == "rft_live_device_token_xyz"


def test_token_rotate_endpoint(client: TestClient) -> None:
    # Rotate on nonexistent provider
    req_unknown = {"provider": "unknown_provider", "buffer_seconds": 60.0}
    resp_unknown = client.post("/api/v1/security/desktop-oauth-device/token/rotate", json=req_unknown)
    assert resp_unknown.status_code == 200
    data_unknown = resp_unknown.json()
    assert data_unknown["status"] == "REVOKED"
    assert data_unknown["rotated"] is False
