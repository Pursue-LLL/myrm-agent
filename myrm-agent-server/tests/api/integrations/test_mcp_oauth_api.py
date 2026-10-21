"""Tests for MCP OAuth authorization API endpoints.

Covers:
- POST /start — PKCE pair generation, state persistence, auth URL building
- GET /callback — State validation, code exchange, token persistence (browser redirect)
- GET /status — OAuth status retrieval for all MCP servers
- DELETE /{server_name} — Token deletion
- Edge cases: expired state, server name mismatch, network errors
- Pending auth garbage collection (_evict_expired_pending)
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations/mcp/oauth"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _clean_pending_auth():
    """Reset module-level _pending_auth state between tests."""
    from app.api.integrations.mcp_oauth import _pending_auth

    _pending_auth.clear()
    yield
    _pending_auth.clear()


class TestStartEndpoint:
    """POST /start — start MCP OAuth authorization flow."""

    def test_start_returns_authorization_url(self, client: TestClient) -> None:
        resp = client.post(
            f"{API_PREFIX}/start",
            json={
                "server_name": "my-mcp",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "client_id": "cid-123",
                "scope": "read write",
                "redirect_uri": "http://localhost:3000/auth/mcp-callback",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "authorization_url" in data
        assert "state" in data

        parsed = urlparse(data["authorization_url"])
        params = parse_qs(parsed.query)
        assert params["response_type"] == ["code"]
        assert params["client_id"] == ["cid-123"]
        assert params["code_challenge_method"] == ["S256"]
        assert params["scope"] == ["read write"]
        assert "code_challenge" in params
        assert params["state"] == [data["state"]]

    def test_start_persists_pending_state(self, client: TestClient) -> None:
        from app.api.integrations.mcp_oauth import _pending_auth

        resp = client.post(
            f"{API_PREFIX}/start",
            json={
                "server_name": "my-mcp",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "client_id": "cid",
                "redirect_uri": "http://localhost:3000/auth/mcp-callback",
            },
        )
        state = resp.json()["data"]["state"]
        assert state in _pending_auth
        pending = _pending_auth[state]
        assert pending["server_name"] == "my-mcp"
        assert pending["client_id"] == "cid"
        assert "code_verifier" in pending
        assert pending["token_endpoint"] == "https://auth.example.com/token"

    def test_start_without_scope(self, client: TestClient) -> None:
        resp = client.post(
            f"{API_PREFIX}/start",
            json={
                "server_name": "no-scope-mcp",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "client_id": "cid",
                "redirect_uri": "http://localhost:3000/auth/mcp-callback",
            },
        )
        assert resp.status_code == 200
        params = parse_qs(urlparse(resp.json()["data"]["authorization_url"]).query)
        assert "scope" not in params

    def test_start_with_client_secret(self, client: TestClient) -> None:
        from app.api.integrations.mcp_oauth import _pending_auth

        resp = client.post(
            f"{API_PREFIX}/start",
            json={
                "server_name": "confidential-mcp",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "client_id": "cid",
                "client_secret": "secret-xyz",
                "redirect_uri": "http://localhost:3000/auth/mcp-callback",
            },
        )
        state = resp.json()["data"]["state"]
        assert _pending_auth[state]["client_secret"] == "secret-xyz"


class TestCallbackEndpoint:
    """GET /callback — exchange auth code for tokens (browser redirect)."""

    def _setup_pending(self, state: str = "test-state") -> str:
        from app.api.integrations.mcp_oauth import _pending_auth

        _pending_auth[state] = {
            "server_name": "my-mcp",
            "code_verifier": "test-verifier-12345",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "cid",
            "client_secret": "",
            "redirect_uri": "http://localhost:3000/auth/mcp-callback",
            "scope": "read",
            "created_at": str(time.time()),
        }
        return state

    def test_callback_exchanges_code_successfully(self, client: TestClient) -> None:
        state = self._setup_pending()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "access-xyz",
            "token_type": "Bearer",
            "refresh_token": "refresh-xyz",
            "expires_in": 3600,
            "scope": "read",
        }

        mock_store = AsyncMock()
        mock_store.save_token_with_config = AsyncMock()

        with (
            patch("app.api.integrations.mcp_oauth.httpx.AsyncClient") as mock_client_cls,
            patch("app.api.integrations.mcp_oauth.get_mcp_oauth_token_store", return_value=mock_store),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resp = client.get(
                f"{API_PREFIX}/callback",
                params={"code": "auth-code-abc", "state": state},
            )

        assert resp.status_code == 200
        assert "Authorization successful" in resp.text or "Authorization Successful" in resp.text or "window.close" in resp.text
        mock_store.save_token_with_config.assert_called_once()

    def test_callback_invalid_state(self, client: TestClient) -> None:
        resp = client.get(
            f"{API_PREFIX}/callback",
            params={"code": "code", "state": "nonexistent-state"},
        )
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.text

    def test_callback_error_param(self, client: TestClient) -> None:
        resp = client.get(
            f"{API_PREFIX}/callback",
            params={"code": "", "state": "s", "error": "access_denied", "error_description": "User denied"},
        )
        assert resp.status_code == 400
        assert "User denied" in resp.text

    def test_callback_expired_state(self, client: TestClient) -> None:
        from app.api.integrations.mcp_oauth import _pending_auth

        state = "expired-state"
        _pending_auth[state] = {
            "server_name": "my-mcp",
            "code_verifier": "v",
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "cid",
            "client_secret": "",
            "redirect_uri": "http://localhost:3000/auth/mcp-callback",
            "scope": "",
            "created_at": str(time.time() - 700),  # 11+ minutes ago
        }
        resp = client.get(
            f"{API_PREFIX}/callback",
            params={"code": "code", "state": state},
        )
        assert resp.status_code == 400
        assert "timed out" in resp.text

    def test_callback_token_exchange_http_failure(self, client: TestClient) -> None:
        state = self._setup_pending()

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"

        with patch("app.api.integrations.mcp_oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resp = client.get(
                f"{API_PREFIX}/callback",
                params={"code": "bad-code", "state": state},
            )
        assert resp.status_code == 400
        assert "Token exchange failed" in resp.text


class TestStatusEndpoint:
    """GET /status — retrieve OAuth status for all servers."""

    def test_status_returns_empty_when_no_tokens(self, client: TestClient) -> None:
        mock_store = AsyncMock()
        mock_store.get_all_statuses = AsyncMock(return_value={})

        with patch("app.api.integrations.mcp_oauth.get_mcp_oauth_token_store", return_value=mock_store):
            resp = client.get(f"{API_PREFIX}/status")

        assert resp.status_code == 200
        assert resp.json()["data"] == {}

    def test_status_returns_server_info(self, client: TestClient) -> None:
        mock_store = AsyncMock()
        mock_store.get_all_statuses = AsyncMock(
            return_value={
                "mcp-1": {"connected": True, "expired": False, "scope": "read"},
                "mcp-2": {"connected": True, "expired": True, "scope": None},
            }
        )

        with patch("app.api.integrations.mcp_oauth.get_mcp_oauth_token_store", return_value=mock_store):
            resp = client.get(f"{API_PREFIX}/status")

        data = resp.json()["data"]
        assert data["mcp-1"]["connected"] is True
        assert data["mcp-1"]["expired"] is False
        assert data["mcp-2"]["expired"] is True


class TestDeleteEndpoint:
    """DELETE /{server_name} — disconnect MCP OAuth."""

    def test_delete_success(self, client: TestClient) -> None:
        mock_store = AsyncMock()
        mock_store.delete_token = AsyncMock()

        with patch("app.api.integrations.mcp_oauth.get_mcp_oauth_token_store", return_value=mock_store):
            resp = client.delete(f"{API_PREFIX}/my-mcp")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["server_name"] == "my-mcp"
        assert data["connected"] is False
        mock_store.delete_token.assert_called_once_with("my-mcp")


class TestPendingAuthGC:
    """Lazy garbage collection of expired pending auth entries."""

    def test_gc_evicts_expired_entries(self) -> None:
        from app.api.integrations.mcp_oauth import (
            _MAX_PENDING,
            _evict_expired_pending,
            _pending_auth,
        )

        _pending_auth.clear()
        now = time.time()
        for i in range(_MAX_PENDING + 5):
            _pending_auth[f"old-state-{i}"] = {
                "server_name": f"s{i}",
                "code_verifier": "v",
                "token_endpoint": "https://a.com/token",
                "client_id": "c",
                "client_secret": "",
                "redirect_uri": "http://localhost:3000/cb",
                "scope": "",
                "created_at": str(now - 700),
            }

        _evict_expired_pending()

        expired_keys = [k for k in _pending_auth if k.startswith("old-state-")]
        assert len(expired_keys) == 0

    def test_gc_does_not_evict_when_below_max(self) -> None:
        from app.api.integrations.mcp_oauth import (
            _evict_expired_pending,
            _pending_auth,
        )

        _pending_auth.clear()
        _pending_auth["keep-me"] = {
            "server_name": "s",
            "code_verifier": "v",
            "token_endpoint": "https://a.com/token",
            "client_id": "c",
            "client_secret": "",
            "redirect_uri": "http://localhost:3000/cb",
            "scope": "",
            "created_at": str(time.time() - 700),
        }

        _evict_expired_pending()

        assert "keep-me" in _pending_auth
