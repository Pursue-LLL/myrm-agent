"""Unit tests for OAuth API — clear_synced_memory parameter."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.integrations.oauth import OAuthCredentialItem
from app.services.agent import oauth_refresher
from app.services.agent.oauth_token_policy import refresh_token_fingerprint
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations"

FRONTEND_CREDENTIAL_RECORD = (
    Path(__file__).resolve().parents[4]
    / "myrm-agent-frontend/src/components/features/settings/sections/integration/credentials/credentialsConstants.ts"
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestOAuthListCredentials:
    """Test GET /oauth used by DataFlow disclosure panel."""

    def test_list_returns_empty_when_no_row(self, client: TestClient):
        with patch(
            "app.api.integrations.oauth.load_oauth_credentials_row",
            new=AsyncMock(return_value=None),
        ):
            response = client.get(f"{API_PREFIX}/oauth")
            assert response.status_code == 200
            assert response.json() == []

    def test_list_returns_connected_items(self, client: TestClient):
        row = type("Row", (), {"config_value": "encrypted", "is_encrypted": True})()
        with (
            patch(
                "app.api.integrations.oauth.load_oauth_credentials_row",
                new=AsyncMock(return_value=row),
            ),
            patch(
                "app.api.integrations.oauth.decrypt_oauth_credentials",
                return_value={
                    "slack": {
                        "token": "tok",
                        "user_id": "U1",
                        "scope": "chat:write",
                        "expires_at": 123.0,
                    },
                    "github": {"user_id": "U2"},
                },
            ),
        ):
            response = client.get(f"{API_PREFIX}/oauth")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            slack = next(item for item in data if item["issuer"] == "slack")
            github = next(item for item in data if item["issuer"] == "github")
            assert slack["connected"] is True
            assert slack["user_id"] == "U1"
            assert github["connected"] is False

    def test_list_tells_renewable_and_rejected_credentials_apart(self, client: TestClient):
        """Access-token expiry only bounds a connection that cannot renew itself."""
        row = type("Row", (), {"config_value": "encrypted", "is_encrypted": True})()
        token_url = "https://auth.example/token"
        stored = {
            "xai": {"token": "a", "refresh_token": "rt_live", "token_url": token_url, "expires_at": 1.0},
            "google_workspace": {"token": "b", "refresh_token": "rt_dead", "token_url": token_url, "expires_at": 1.0},
            "pasted": {"token": "c", "expires_at": 1.0},
        }
        oauth_refresher._rejected_refresh_tokens["google_workspace"] = refresh_token_fingerprint("rt_dead")
        with (
            patch(
                "app.api.integrations.oauth.load_oauth_credentials_row",
                new=AsyncMock(return_value=row),
            ),
            patch("app.api.integrations.oauth.decrypt_oauth_credentials", return_value=stored),
        ):
            response = client.get(f"{API_PREFIX}/oauth")

        assert response.status_code == 200
        flags = {item["issuer"]: (item["renewable"], item["needs_reauth"]) for item in response.json()}
        assert flags == {
            "xai": (True, False),
            "google_workspace": (True, True),
            "pasted": (False, False),
        }


class TestOAuthListContract:
    def test_frontend_record_declares_every_field_the_list_returns(self):
        """The Credentials card reads these keys by name; a field the UI type lacks is silently ignored."""
        record_type = FRONTEND_CREDENTIAL_RECORD.read_text(encoding="utf-8").split("export type OauthCredentialRecord", 1)[1]
        record_type = record_type.split("};", 1)[0]

        missing = [name for name in OAuthCredentialItem.model_fields if not re.search(rf"\b{name}\??:", record_type)]

        assert missing == []


class TestOAuthDeleteClearSyncedMemory:
    """Test DELETE /oauth/{issuer} with clear_synced_memory parameter."""

    def test_delete_no_credentials_row_returns_404(self, client: TestClient):
        with patch(
            "app.api.integrations.oauth.remove_oauth_credential",
            new=AsyncMock(return_value=False),
        ):
            response = client.delete(f"{API_PREFIX}/oauth/github")
            assert response.status_code == 404

    def test_delete_success_no_memory_clear(self, client: TestClient):
        with patch(
            "app.api.integrations.oauth.remove_oauth_credential",
            new=AsyncMock(return_value=True),
        ):
            response = client.delete(f"{API_PREFIX}/oauth/github")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["trees_removed"] == 0

    def test_delete_with_clear_synced_memory(self, client: TestClient):
        mock_mem_svc = AsyncMock()
        mock_mem_svc.remove_trees_by_provider = AsyncMock(return_value=5)

        with (
            patch(
                "app.api.integrations.oauth.remove_oauth_credential",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.services.memory.imports.integration_memory.get_integration_memory_service",
                new=AsyncMock(return_value=mock_mem_svc),
            ),
        ):
            response = client.delete(f"{API_PREFIX}/oauth/github?clear_synced_memory=true")
            assert response.status_code == 200
            data = response.json()
            assert data["trees_removed"] == 5
            mock_mem_svc.remove_trees_by_provider.assert_called_once_with("github")
