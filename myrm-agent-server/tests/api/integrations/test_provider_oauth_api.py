"""Unit tests for Provider OAuth API — Anthropic PKCE, OpenAI Device Code, GitHub Copilot Device Code."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.integrations.provider_oauth import (
    _pending_device_flows,
    _pending_pkce_flows,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations/provider-oauth"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with loopback auth mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _clean_pending_flows():
    _pending_device_flows.clear()
    _pending_pkce_flows.clear()
    yield
    _pending_device_flows.clear()
    _pending_pkce_flows.clear()


class TestProviderOAuthStatusAndDisconnect:
    """Test GET /status/{provider} and DELETE /disconnect/{provider}."""

    def test_status_disconnected(self, client: TestClient):
        with patch(
            "app.api.integrations.provider_oauth.is_oauth_issuer_connected",
            new=AsyncMock(return_value=False),
        ):
            resp = client.get(f"{API_PREFIX}/status/anthropic")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["provider"] == "anthropic"
            assert data["connected"] is False

    def test_status_connected_with_details(self, client: TestClient):
        row = type("Row", (), {"config_value": "encrypted", "is_encrypted": True})()
        with (
            patch(
                "app.api.integrations.provider_oauth.is_oauth_issuer_connected",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.api.integrations.provider_oauth.load_oauth_credentials_row",
                new=AsyncMock(return_value=row),
            ),
            patch(
                "app.api.integrations.provider_oauth.decrypt_oauth_credentials",
                return_value={
                    "provider_copilot": {
                        "expires_at": 1800000000,
                        "scope": "read:user",
                        "base_url": "https://api.githubcopilot.com",
                        "available_models": ["gpt-4o", "claude-3.5-sonnet"],
                    }
                },
            ),
        ):
            resp = client.get(f"{API_PREFIX}/status/copilot")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["provider"] == "copilot"
            assert data["connected"] is True
            assert data["available_models"] == ["gpt-4o", "claude-3.5-sonnet"]
            assert data["base_url"] == "https://api.githubcopilot.com"

    def test_status_unknown_provider_400(self, client: TestClient):
        resp = client.get(f"{API_PREFIX}/status/unknown_provider")
        assert resp.status_code == 400
        body = resp.json()
        assert "Unknown provider" in (body.get("detail") or body.get("message") or "")

    def test_disconnect_success(self, client: TestClient):
        with patch(
            "app.api.integrations.provider_oauth.delete_oauth_credential",
            new=AsyncMock(return_value=True),
        ):
            resp = client.delete(f"{API_PREFIX}/disconnect/openai")
            assert resp.status_code == 200
            assert resp.json()["data"]["connected"] is False

    def test_disconnect_not_found_404(self, client: TestClient):
        with patch(
            "app.api.integrations.provider_oauth.delete_oauth_credential",
            new=AsyncMock(return_value=False),
        ):
            resp = client.delete(f"{API_PREFIX}/disconnect/openai")
            assert resp.status_code == 404
            body = resp.json()
            assert "not connected" in (body.get("detail") or body.get("message") or "")


class TestAnthropicPKCEFlow:
    """Test Anthropic PKCE start and callback."""

    def test_start_pkce_returns_authorize_url(self, client: TestClient):
        resp = client.post(f"{API_PREFIX}/anthropic/start")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "authorize_url" in data
        assert "state" in data
        assert data["state"] in _pending_pkce_flows
        assert "claude.ai/oauth/authorize" in data["authorize_url"]


class TestOpenAIDeviceCodeFlow:
    """Test OpenAI device code start."""

    def test_start_openai_device_code(self, client: TestClient):
        from httpx import Request, Response

        mock_resp = Response(
            200,
            json={
                "device_auth_id": "auth-123",
                "user_code": "WDJB-ABCD",
                "interval": 5,
                "expires_in": 900,
            },
            request=Request("POST", "https://auth.openai.com/api/accounts/deviceauth/usercode"),
        )

        with patch("app.api.integrations.provider_oauth.httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http_cls.return_value = mock_http

            resp = client.post(f"{API_PREFIX}/openai/start")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["user_code"] == "WDJB-ABCD"
            assert "auth.openai.com/codex/device" in data["verification_uri"]
            assert "WDJB-ABCD" in _pending_device_flows


class TestCopilotDeviceCodeFlow:
    """Test Copilot device code start."""

    def test_start_copilot_device_code(self, client: TestClient):
        from httpx import Request, Response

        mock_resp = Response(
            200,
            json={
                "device_code": "dc-copilot-123",
                "user_code": "1234-5678",
                "verification_uri": "https://github.com/login/device",
                "interval": 5,
                "expires_in": 900,
            },
            request=Request("POST", "https://github.com/login/device/code"),
        )

        with patch("app.api.integrations.provider_oauth.httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http_cls.return_value = mock_http

            resp = client.post(f"{API_PREFIX}/copilot/start")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["user_code"] == "1234-5678"
            assert data["verification_uri"] == "https://github.com/login/device"
            assert "copilot_1234-5678" in _pending_device_flows
