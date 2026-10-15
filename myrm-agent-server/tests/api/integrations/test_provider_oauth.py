"""Unit tests for the Provider OAuth API — status, disconnect and E2E fixtures."""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations/provider-oauth"

_RETIRED_PROVIDERS = ("anthropic", "openai", "copilot")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestRetiredSubscriptionLogins:
    """The in-process Claude / ChatGPT / Copilot logins are gone and must not be re-mounted."""

    @pytest.mark.parametrize("provider", _RETIRED_PROVIDERS)
    @pytest.mark.parametrize("action", ["start", "poll"])
    def test_login_routes_do_not_exist(self, client: TestClient, provider: str, action: str) -> None:
        assert client.post(f"{API_PREFIX}/{provider}/{action}").status_code == 404

    def test_anthropic_callback_route_does_not_exist(self, client: TestClient) -> None:
        assert client.get(f"{API_PREFIX}/anthropic/callback?code=c&state=s").status_code == 404

    @pytest.mark.parametrize("provider", _RETIRED_PROVIDERS)
    def test_status_and_disconnect_reject_retired_providers(self, client: TestClient, provider: str) -> None:
        for response in (
            client.get(f"{API_PREFIX}/status/{provider}"),
            client.delete(f"{API_PREFIX}/disconnect/{provider}"),
        ):
            assert response.status_code == 400
            assert "Unknown provider" in response.text


class TestXaiLoginLivesInXaiOauth:
    """The xAI device-code login is served by /integrations/xai/oauth only."""

    @pytest.mark.parametrize("action", ["start", "poll"])
    def test_provider_oauth_has_no_login_routes(self, client: TestClient, action: str) -> None:
        assert client.post(f"{API_PREFIX}/xai/{action}").status_code == 404


class TestStatusAndDisconnect:
    """GET /status/{provider} and DELETE /disconnect/{provider}."""

    def test_status_disconnected(self, client: TestClient) -> None:
        with patch("app.api.integrations.provider_oauth.is_oauth_issuer_connected", new=AsyncMock(return_value=False)):
            response = client.get(f"{API_PREFIX}/status/xai")

        assert response.status_code == 200
        assert response.json()["data"] == {"provider": "xai", "issuer": "xai", "connected": False}

    def test_status_connected_xai(self, client: TestClient) -> None:
        row = type("Row", (), {"config_value": "enc", "is_encrypted": True})()
        expires_at = time.time() + 3600
        with (
            patch("app.api.integrations.provider_oauth.is_oauth_issuer_connected", new=AsyncMock(return_value=True)),
            patch("app.api.integrations.provider_oauth.load_oauth_credentials_row", new=AsyncMock(return_value=row)),
            patch(
                "app.api.integrations.provider_oauth.decrypt_oauth_credentials",
                return_value={
                    "xai": {
                        "token": "xai-tok-123",
                        "expires_at": expires_at,
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
        assert data["expires_at"] == expires_at
        assert data["scope"] == "api:access"
        assert data["base_url"] == "https://api.x.ai/v1"
        assert "available_models" not in data
        assert "token" not in data

    def test_status_unknown_provider(self, client: TestClient) -> None:
        response = client.get(f"{API_PREFIX}/status/unknown_provider")
        assert response.status_code == 400
        assert "Unknown provider" in response.text

    def test_disconnect_success(self, client: TestClient) -> None:
        with patch(
            "app.api.integrations.provider_oauth.delete_oauth_credential", new=AsyncMock(return_value=True)
        ) as mock_delete:
            response = client.delete(f"{API_PREFIX}/disconnect/xai")

        assert response.status_code == 200
        assert response.json()["data"] == {"provider": "xai", "connected": False}
        assert mock_delete.call_args[0][1] == "xai"

    def test_disconnect_unknown_provider(self, client: TestClient) -> None:
        response = client.delete(f"{API_PREFIX}/disconnect/unknown_provider")
        assert response.status_code == 400
        assert "Unknown provider" in response.text

    def test_disconnect_not_connected(self, client: TestClient) -> None:
        with patch("app.api.integrations.provider_oauth.delete_oauth_credential", new=AsyncMock(return_value=False)):
            response = client.delete(f"{API_PREFIX}/disconnect/xai")

        assert response.status_code == 404
        assert response.json()["code"] == 40401


class TestE2eFixtureEndpoints:
    """Local-mode-only seed / cleanup endpoints used by the Chrome E2E lanes."""

    def test_seed_and_cleanup_xai(self, client: TestClient) -> None:
        with (
            patch("app.config.deploy_mode.is_local_mode", return_value=True),
            patch("app.api.integrations.provider_oauth.upsert_oauth_credential", new=AsyncMock()) as mock_upsert,
            patch("app.api.integrations.provider_oauth.delete_oauth_credential", new=AsyncMock(return_value=True)) as mock_delete,
        ):
            seed_resp = client.post(f"{API_PREFIX}/test/seed-oauth?token=test-tok")
            clean_resp = client.post(f"{API_PREFIX}/test/cleanup-oauth")

        assert seed_resp.status_code == 200
        assert seed_resp.json()["data"] == {"provider": "xai", "issuer": "xai", "seeded": True}
        issuer, entry = mock_upsert.call_args[0][1:]
        assert issuer == "xai"
        assert entry["token"] == "test-tok"
        assert entry["base_url"] == "https://api.x.ai/v1"
        assert "available_models" not in entry
        assert entry["expires_at"] > entry["connected_at"]

        assert clean_resp.status_code == 200
        assert clean_resp.json()["data"] == {"provider": "xai", "issuer": "xai", "cleaned": True}
        assert mock_delete.call_args[0][1] == "xai"

    def test_seed_honours_explicit_base_url(self, client: TestClient) -> None:
        with (
            patch("app.config.deploy_mode.is_local_mode", return_value=True),
            patch("app.api.integrations.provider_oauth.upsert_oauth_credential", new=AsyncMock()) as mock_upsert,
        ):
            response = client.post(f"{API_PREFIX}/test/seed-oauth?base_url=http://127.0.0.1:9/v1")

        assert response.status_code == 200
        assert mock_upsert.call_args[0][2]["base_url"] == "http://127.0.0.1:9/v1"

    @pytest.mark.parametrize("path", ["test/seed-oauth", "test/cleanup-oauth"])
    def test_hidden_outside_local_mode(self, client: TestClient, path: str) -> None:
        with patch("app.config.deploy_mode.is_local_mode", return_value=False):
            assert client.post(f"{API_PREFIX}/{path}").status_code == 404

    @pytest.mark.parametrize("path", ["test/seed-oauth", "test/cleanup-oauth"])
    def test_reject_unknown_provider(self, client: TestClient, path: str) -> None:
        with patch("app.config.deploy_mode.is_local_mode", return_value=True):
            response = client.post(f"{API_PREFIX}/{path}?provider=openai")

        assert response.status_code == 400
        assert "Unknown provider" in response.text
