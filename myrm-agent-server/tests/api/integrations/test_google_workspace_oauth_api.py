"""Tests for Google Workspace OAuth authorization API."""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.integrations.google_workspace_oauth import (
    GOOGLE_WORKSPACE_ISSUER,
    _pending_auth,
    _successful_auth,
    _successful_auth_meta,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations/google-workspace/oauth"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _clean_oauth_state() -> Iterator[None]:
    _pending_auth.clear()
    _successful_auth.clear()
    _successful_auth_meta.clear()
    yield
    _pending_auth.clear()
    _successful_auth.clear()
    _successful_auth_meta.clear()


@pytest.fixture
def google_oauth_configured() -> Iterator[None]:
    with (
        patch("app.api.integrations.google_workspace_oauth_flow.settings.google_client_id", "test-client-id"),
        patch(
            "app.api.integrations.google_workspace_oauth_flow.settings.google_client_secret",
            SecretStr("test-client-secret"),
        ),
    ):
        yield


class TestGoogleWorkspaceOAuthConfig:
    def test_config_reports_not_configured(self, client: TestClient) -> None:
        with (
            patch("app.api.integrations.google_workspace_oauth_flow.settings.google_client_id", ""),
            patch(
                "app.api.integrations.google_workspace_oauth_flow.settings.google_client_secret",
                SecretStr(""),
            ),
        ):
            resp = client.get(f"{API_PREFIX}/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["configured"] is False
        assert data["issuer"] == GOOGLE_WORKSPACE_ISSUER

    def test_config_reports_configured(self, client: TestClient, google_oauth_configured: None) -> None:
        resp = client.get(f"{API_PREFIX}/config")
        assert resp.status_code == 200
        assert resp.json()["data"]["configured"] is True


class TestGoogleWorkspaceOAuthStart:
    def test_start_requires_server_config(self, client: TestClient) -> None:
        with (
            patch("app.api.integrations.google_workspace_oauth_flow.settings.google_client_id", ""),
            patch(
                "app.api.integrations.google_workspace_oauth_flow.settings.google_client_secret",
                SecretStr(""),
            ),
        ):
            resp = client.post(f"{API_PREFIX}/start")
        assert resp.status_code == 503

    def test_start_returns_google_auth_url(self, client: TestClient, google_oauth_configured: None) -> None:
        resp = client.post(f"{API_PREFIX}/start")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "authorization_url" in data
        assert "state" in data

        parsed = urlparse(data["authorization_url"])
        assert parsed.netloc == "accounts.google.com"
        params = parse_qs(parsed.query)
        assert params["client_id"] == ["test-client-id"]
        assert params["access_type"] == ["offline"]
        assert params["prompt"] == ["consent"]
        assert params["code_challenge_method"] == ["S256"]

    def test_start_write_tier_includes_write_scopes(self, client: TestClient, google_oauth_configured: None) -> None:
        resp = client.post(f"{API_PREFIX}/start", json={"tier": "write"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data.get("tier") == "write"

        parsed = urlparse(data["authorization_url"])
        params = parse_qs(parsed.query)
        scope = params["scope"][0]
        assert "https://www.googleapis.com/auth/gmail.send" in scope
        assert "https://www.googleapis.com/auth/calendar.events" in scope
        with patch(
            "app.api.integrations.google_workspace_oauth_flow.get_public_ingress_base_url",
            new=AsyncMock(return_value="https://tenant.example.com"),
        ):
            resp = client.post(f"{API_PREFIX}/start")
        assert resp.status_code == 200
        state = resp.json()["data"]["state"]
        assert _pending_auth[state]["redirect_uri"] == (
            "https://tenant.example.com/api/v1/integrations/google-workspace/oauth/callback"
        )


class TestGoogleWorkspaceOAuthCallback:
    def test_callback_persists_credentials(self, client: TestClient, google_oauth_configured: None) -> None:
        start = client.post(f"{API_PREFIX}/start").json()["data"]
        state = start["state"]
        pending = _pending_auth[state]
        code_verifier = pending["code_verifier"]

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "access-123",
            "refresh_token": "refresh-456",
            "expires_in": 3600,
            "scope": "calendar.readonly",
        }

        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {"email": "user@example.com"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=token_response)
        mock_client.get = AsyncMock(return_value=userinfo_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        upsert_mock = AsyncMock()

        enable_mock = AsyncMock(return_value=(True, False))

        with (
            patch("app.api.integrations.google_workspace_oauth.httpx.AsyncClient", return_value=mock_client),
            patch(
                "app.api.integrations.google_workspace_oauth.upsert_oauth_credential",
                upsert_mock,
            ),
            patch(
                "app.api.integrations.google_workspace_oauth._maybe_enable_google_workspace_skill",
                enable_mock,
            ),
        ):
            resp = client.get(
                f"{API_PREFIX}/callback",
                params={"code": "auth-code", "state": state},
            )

        assert resp.status_code == 200
        assert "Authorization Successful" in resp.text
        upsert_mock.assert_awaited_once()
        call_args = upsert_mock.await_args
        assert call_args is not None
        assert call_args.args[1] == GOOGLE_WORKSPACE_ISSUER
        saved = call_args.args[2]
        assert saved["token"] == "access-123"
        assert saved["refresh_token"] == "refresh-456"
        assert saved["token_url"] == "https://oauth2.googleapis.com/token"
        assert "client_secret" not in saved
        assert "client_id" not in saved
        assert saved["user_id"] == "user@example.com"
        assert code_verifier
        enable_mock.assert_awaited_once()

        status = client.get(f"{API_PREFIX}/status/{state}").json()["data"]
        assert status["status"] == "success"
        assert status["skill_auto_enabled"] is True
        assert status["skill_was_user_disabled"] is False

    def test_callback_skips_enable_when_user_disabled_skill(
        self, client: TestClient, google_oauth_configured: None
    ) -> None:
        start = client.post(f"{API_PREFIX}/start").json()["data"]
        state = start["state"]

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "access-123",
            "refresh_token": "refresh-456",
            "expires_in": 3600,
        }
        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {"email": "user@example.com"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=token_response)
        mock_client.get = AsyncMock(return_value=userinfo_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.api.integrations.google_workspace_oauth.httpx.AsyncClient", return_value=mock_client),
            patch("app.api.integrations.google_workspace_oauth.upsert_oauth_credential", AsyncMock()),
            patch(
                "app.api.integrations.google_workspace_oauth._maybe_enable_google_workspace_skill",
                AsyncMock(return_value=(False, True)),
            ),
        ):
            resp = client.get(
                f"{API_PREFIX}/callback",
                params={"code": "auth-code", "state": state},
            )
        assert resp.status_code == 200
        status = client.get(f"{API_PREFIX}/status/{state}").json()["data"]
        assert status["skill_auto_enabled"] is False
        assert status["skill_was_user_disabled"] is True


class TestGoogleWorkspaceOAuthStatus:
    def test_state_status_success_after_callback(self, client: TestClient, google_oauth_configured: None) -> None:
        start = client.post(f"{API_PREFIX}/start").json()["data"]
        state = start["state"]
        _successful_auth[state] = time.time()
        resp = client.get(f"{API_PREFIX}/status/{state}")
        assert resp.json()["data"]["status"] == "success"

    def test_callback_invalid_state_returns_400(self, client: TestClient, google_oauth_configured: None) -> None:
        resp = client.get(
            f"{API_PREFIX}/callback",
            params={"code": "auth-code", "state": "invalid-state"},
        )
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.text

    def test_connection_status_not_connected(self, client: TestClient) -> None:
        with patch(
            "app.api.integrations.google_workspace_oauth.load_oauth_credentials_row",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get(f"{API_PREFIX}/status")
        assert resp.status_code == 200
        assert resp.json()["data"]["connected"] is False
