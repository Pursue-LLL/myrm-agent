"""Unit tests for OAuth API — clear_synced_memory parameter."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
API_PREFIX = "/api/v1/integrations"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestOAuthDeleteClearSyncedMemory:
    """Test DELETE /oauth/{issuer} with clear_synced_memory parameter."""

    def test_delete_no_credentials_row_returns_404(self, client: TestClient):
        with patch("app.api.integrations.oauth._load_row", return_value=None):
            response = client.delete(f"{API_PREFIX}/oauth/github")
            assert response.status_code == 404

    def test_delete_nonexistent_issuer_returns_404(self, client: TestClient):
        with (
            patch("app.api.integrations.oauth._load_row") as mock_load,
            patch(
                "app.api.integrations.oauth._decrypt_credentials",
                return_value={"slack": {"token": "xxx"}},
            ),
            patch("app.api.integrations.oauth.get_encryption_service"),
        ):
            mock_row = MagicMock()
            mock_row.config_value = {"slack": {"token": "xxx"}}
            mock_row.is_encrypted = False
            mock_load.return_value = mock_row

            response = client.delete(f"{API_PREFIX}/oauth/github")
            assert response.status_code == 404

    def test_delete_success_no_memory_clear(self, client: TestClient):
        """Successful delete without clearing synced memory."""
        MagicMock()

        with (
            patch("app.api.integrations.oauth._load_row") as mock_load,
            patch(
                "app.api.integrations.oauth._decrypt_credentials",
                return_value={"github": {"token": "t"}},
            ),
            patch(
                "app.api.integrations.oauth._encrypt_credentials",
                return_value=({"_cipher": "enc"}, True),
            ),
            patch("app.api.integrations.oauth.get_encryption_service"),
        ):
            mock_row = MagicMock()
            mock_row.config_value = {"github": {"token": "t"}}
            mock_row.is_encrypted = False
            mock_load.return_value = mock_row

            response = client.delete(f"{API_PREFIX}/oauth/github")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["trees_removed"] == 0

    def test_delete_with_clear_synced_memory(self, client: TestClient):
        """Successful delete with clear_synced_memory=true."""
        mock_mem_svc = AsyncMock()
        mock_mem_svc.remove_trees_by_provider = AsyncMock(return_value=5)

        with (
            patch("app.api.integrations.oauth._load_row") as mock_load,
            patch(
                "app.api.integrations.oauth._decrypt_credentials",
                return_value={"github": {"token": "t"}},
            ),
            patch(
                "app.api.integrations.oauth._encrypt_credentials",
                return_value=({"_cipher": "enc"}, True),
            ),
            patch("app.api.integrations.oauth.get_encryption_service"),
            patch(
                "app.services.memory.integration_memory.get_integration_memory_service",
                new=AsyncMock(return_value=mock_mem_svc),
            ),
        ):
            mock_row = MagicMock()
            mock_row.config_value = {"github": {"token": "t"}}
            mock_row.is_encrypted = False
            mock_load.return_value = mock_row

            response = client.delete(f"{API_PREFIX}/oauth/github?clear_synced_memory=true")
            assert response.status_code == 200
            data = response.json()
            assert data["trees_removed"] == 5
            mock_mem_svc.remove_trees_by_provider.assert_called_once_with("github")
