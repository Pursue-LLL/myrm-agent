"""Unit tests for Provider OAuth API — Anthropic PKCE, OpenAI Device Code, Copilot Device Code, Status, and Disconnect."""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations/provider-oauth"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestAnthropicOAuth:
    """Test Anthropic PKCE OAuth flow endpoints."""

    def test_start_anthropic_oauth(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/anthropic/start")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "authorize_url" in data
        assert "state" in data
        assert "code_challenge=" in data["authorize_url"]
        assert data["state"] in data["authorize_url"]

    def test_callback_missing_params(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/anthropic/callback")
        assert response.status_code == 400
        assert "Missing authorization code or state" in response.text

    def test_callback_invalid_state(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/anthropic/callback?code=test-code&state=nonexistent-state")
        assert response.status_code == 400
        assert "Invalid or expired authorization state" in response.text

    def test_callback_success(self, client: TestClient):
        # 1. Start flow to register state in _pending_pkce_flows
        start_resp = client.post(f"{API_PREFIX}/anthropic/start")
        state = start_resp.json()["data"]["state"]

        # 2. Mock token exchange HTTP call and DB persistence
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "sk-ant-oauth-token-123",
            "refresh_token": "ant-refresh-token-456",
            "expires_in": 3600,
        }

        with (
            patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)),
            patch("app.api.integrations.provider_oauth.upsert_oauth_credential", new=AsyncMock()) as mock_upsert,
        ):
            response = client.get(f"{API_PREFIX}/anthropic/callback?code=auth-code-123&state={state}")
            assert response.status_code == 200
            assert "Anthropic Connected" in response.text
            assert mock_upsert.called
            call_args = mock_upsert.call_args[0]
            assert call_args[1] == "provider_anthropic"
            assert call_args[2]["token"] == "sk-ant-oauth-token-123"

    def test_callback_token_exchange_failure(self, client: TestClient):
        start_resp = client.post(f"{API_PREFIX}/anthropic/start")
        state = start_resp.json()["data"]["state"]

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            response = client.get(f"{API_PREFIX}/anthropic/callback?code=bad-code&state={state}")
            assert response.status_code == 400
            assert "Failed to exchange authorization code" in response.text


class TestOpenAIOAuth:
    """Test OpenAI Device Code flow endpoints."""

    def test_start_openai_device_code_success(self, client: TestClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "device_auth_id": "dev-auth-id-abc",
            "user_code": "WDJB-ABCD",
            "interval": 5,
        }
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            response = client.post(f"{API_PREFIX}/openai/start")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["user_code"] == "WDJB-ABCD"
            assert "verification_uri" in data

    def test_poll_openai_not_found(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/openai/poll?user_code=NONEXISTENT")
        assert response.status_code == 404

    def test_poll_openai_pending(self, client: TestClient):
        # 1. Start flow to register user_code
        start_resp_mock = MagicMock()
        start_resp_mock.status_code = 200
        start_resp_mock.json.return_value = {
            "device_auth_id": "dev-auth-id-123",
            "user_code": "OPENAI-PENDING",
            "interval": 5,
        }
        start_resp_mock.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=start_resp_mock)):
            client.post(f"{API_PREFIX}/openai/start")

        # 2. Poll returning 400 authorization_pending
        poll_resp_mock = MagicMock()
        poll_resp_mock.status_code = 400
        poll_resp_mock.json.return_value = {"error": {"code": "authorization_pending"}}

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=poll_resp_mock)):
            response = client.post(f"{API_PREFIX}/openai/poll?user_code=OPENAI-PENDING")
            assert response.status_code == 200
            assert response.json()["data"]["status"] == "pending"

    def test_poll_openai_success(self, client: TestClient):
        start_resp_mock = MagicMock()
        start_resp_mock.status_code = 200
        start_resp_mock.json.return_value = {
            "device_auth_id": "dev-auth-id-success",
            "user_code": "OPENAI-OK",
            "interval": 5,
        }
        start_resp_mock.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=start_resp_mock)):
            client.post(f"{API_PREFIX}/openai/start")

        # Device token exchange returns auth code
        device_resp = MagicMock()
        device_resp.status_code = 200
        device_resp.json.return_value = {
            "authorization_code": "auth-code-xyz",
            "code_verifier": "verifier-xyz",
        }

        # Token endpoint returns access token
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "openai-oauth-token-val",
            "refresh_token": "openai-refresh-val",
            "expires_in": 3600,
        }

        async def _mock_post(url, **kwargs):
            if "deviceauth/token" in str(url):
                return device_resp
            return token_resp

        with (
            patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_mock_post)),
            patch("app.api.integrations.provider_oauth.upsert_oauth_credential", new=AsyncMock()) as mock_upsert,
        ):
            response = client.post(f"{API_PREFIX}/openai/poll?user_code=OPENAI-OK")
            assert response.status_code == 200
            assert response.json()["data"]["status"] == "success"
            assert mock_upsert.called
            call_args = mock_upsert.call_args[0]
            assert call_args[1] == "provider_openai"
            assert call_args[2]["token"] == "openai-oauth-token-val"


class TestCopilotOAuth:
    """Test GitHub Copilot Device Code flow endpoints."""

    def test_start_copilot_device_code(self, client: TestClient):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "device_code": "copilot-dev-code-123",
            "user_code": "CP-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            response = client.post(f"{API_PREFIX}/copilot/start")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["user_code"] == "CP-1234"
            assert data["verification_uri"] == "https://github.com/login/device"

    def test_poll_copilot_pending(self, client: TestClient):
        start_resp = MagicMock()
        start_resp.status_code = 200
        start_resp.json.return_value = {
            "device_code": "copilot-dev-pending",
            "user_code": "CP-PEND",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
        start_resp.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=start_resp)):
            client.post(f"{API_PREFIX}/copilot/start")

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.headers = {"content-type": "application/json"}
        poll_resp.json.return_value = {"error": "authorization_pending"}

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=poll_resp)):
            response = client.post(f"{API_PREFIX}/copilot/poll?user_code=CP-PEND")
            assert response.status_code == 200
            assert response.json()["data"]["status"] == "pending"

    def test_poll_copilot_success(self, client: TestClient):
        start_resp = MagicMock()
        start_resp.status_code = 200
        start_resp.json.return_value = {
            "device_code": "copilot-dev-success",
            "user_code": "CP-OK",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }
        start_resp.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=start_resp)):
            client.post(f"{API_PREFIX}/copilot/start")

        github_poll_resp = MagicMock()
        github_poll_resp.status_code = 200
        github_poll_resp.headers = {"content-type": "application/json"}
        github_poll_resp.json.return_value = {"access_token": "gh-oauth-access-token"}

        with (
            patch("httpx.AsyncClient.post", new=AsyncMock(return_value=github_poll_resp)),
            patch(
                "app.api.integrations.provider_oauth._exchange_copilot_token",
                new=AsyncMock(return_value=("copilot-token-789", time.time() + 1800, "https://api.individual.githubcopilot.com")),
            ),
            patch(
                "app.api.integrations.provider_oauth._fetch_copilot_models",
                new=AsyncMock(return_value=["gpt-4o", "claude-3.5-sonnet"]),
            ),
            patch("app.api.integrations.provider_oauth.upsert_oauth_credential", new=AsyncMock()) as mock_upsert,
        ):
            response = client.post(f"{API_PREFIX}/copilot/poll?user_code=CP-OK")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["status"] == "success"
            assert "gpt-4o" in data["available_models"]
            assert mock_upsert.called
            call_args = mock_upsert.call_args[0]
            assert call_args[1] == "provider_copilot"
            assert call_args[2]["token"] == "copilot-token-789"
            assert call_args[2]["base_url"] == "https://api.individual.githubcopilot.com"


class TestProviderOAuthStatusAndDisconnect:
    """Test status and disconnect endpoints for all providers."""

    def test_status_disconnected(self, client: TestClient):
        with patch("app.api.integrations.provider_oauth.is_oauth_issuer_connected", new=AsyncMock(return_value=False)):
            response = client.get(f"{API_PREFIX}/status/anthropic")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["provider"] == "anthropic"
            assert data["connected"] is False

    def test_status_connected(self, client: TestClient):
        row = type("Row", (), {"config_value": "enc", "is_encrypted": True})()
        with (
            patch("app.api.integrations.provider_oauth.is_oauth_issuer_connected", new=AsyncMock(return_value=True)),
            patch("app.api.integrations.provider_oauth.load_oauth_credentials_row", new=AsyncMock(return_value=row)),
            patch(
                "app.api.integrations.provider_oauth.decrypt_oauth_credentials",
                return_value={
                    "provider_copilot": {
                        "token": "tok",
                        "expires_at": time.time() + 3600,
                        "scope": "copilot",
                        "base_url": "https://api.individual.githubcopilot.com",
                        "available_models": ["gpt-4o", "claude-3.5-sonnet"],
                    }
                },
            ),
        ):
            response = client.get(f"{API_PREFIX}/status/copilot")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["connected"] is True
            assert "gpt-4o" in data["available_models"]
            assert data["base_url"] == "https://api.individual.githubcopilot.com"

    def test_status_unknown_provider(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/status/unknown_provider")
        assert response.status_code == 400
        assert "Unknown provider" in response.text

    def test_disconnect_success(self, client: TestClient):
        with patch("app.api.integrations.provider_oauth.delete_oauth_credential", new=AsyncMock(return_value=True)) as mock_delete:
            response = client.delete(f"{API_PREFIX}/disconnect/openai")
            assert response.status_code == 200
            assert response.json()["data"]["connected"] is False
            assert mock_delete.called
            assert mock_delete.call_args[0][1] == "provider_openai"

    def test_disconnect_unknown_provider(self, client: TestClient):
        response = client.delete(f"{API_PREFIX}/disconnect/unknown_provider")
        assert response.status_code == 400
        assert "Unknown provider" in response.text

    def test_disconnect_not_connected(self, client: TestClient):
        with patch("app.api.integrations.provider_oauth.delete_oauth_credential", new=AsyncMock(return_value=False)):
            response = client.delete(f"{API_PREFIX}/disconnect/openai")
            assert response.status_code == 404
            assert response.json()["code"] == 40401

    def test_status_connected_xai(self, client: TestClient):
        row = type("Row", (), {"config_value": "enc", "is_encrypted": True})()
        with (
            patch("app.api.integrations.provider_oauth.is_oauth_issuer_connected", new=AsyncMock(return_value=True)),
            patch("app.api.integrations.provider_oauth.load_oauth_credentials_row", new=AsyncMock(return_value=row)),
            patch(
                "app.api.integrations.provider_oauth.decrypt_oauth_credentials",
                return_value={
                    "xai": {
                        "token": "xai-tok-123",
                        "expires_at": time.time() + 3600,
                        "scope": "api:access",
                        "base_url": "https://api.x.ai/v1",
                    }
                },
            ),
        ):
            response = client.get(f"{API_PREFIX}/status/xai")
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["connected"] is True
            assert data["provider"] == "xai"
            assert data["issuer"] == "xai"
            assert "grok-2" in data["available_models"]
            assert data["base_url"] == "https://api.x.ai/v1"

    def test_xai_start_and_poll_routes(self, client: TestClient):
        from app.core.utils.response_utils import success_response

        with (
            patch(
                "app.api.integrations.xai_oauth.start_xai_oauth",
                new=AsyncMock(return_value=success_response(data={"user_code": "XAI-123", "verification_uri": "https://auth.x.ai/device"})),
            ),
            patch(
                "app.api.integrations.xai_oauth.poll_xai_oauth",
                new=AsyncMock(return_value=success_response(data={"status": "pending"})),
            ),
        ):
            start_resp = client.post(f"{API_PREFIX}/xai/start")
            assert start_resp.status_code == 200
            assert start_resp.json()["data"]["user_code"] == "XAI-123"

            poll_resp = client.post(f"{API_PREFIX}/xai/poll?user_code=XAI-123")
            assert poll_resp.status_code == 200
            assert poll_resp.json()["data"]["status"] == "pending"
