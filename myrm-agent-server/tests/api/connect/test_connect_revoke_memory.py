"""Unit tests for connect revoke with clear_synced_memory."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="connect")
API_PREFIX = "/api/v1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestConnectRevokeClearMemory:
    """Tests for POST /connect/revoke clear_synced_memory parameter."""

    def test_revoke_unknown_no_memory_clear(self, client: TestClient):
        """Unknown profile: revoked=false, no memory clear even if requested."""
        response = client.post(
            f"{API_PREFIX}/connect/revoke",
            json={"profile_id": "nonexistent", "clear_synced_memory": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["revoked"] is False
        assert data["trees_removed"] == 0

    def test_revoke_default_no_clear(self, client: TestClient):
        """Default clear_synced_memory is False."""
        response = client.post(
            f"{API_PREFIX}/connect/revoke",
            json={"profile_id": "cursor"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trees_removed"] == 0

    def test_revoke_with_clear_calls_service(self, client: TestClient):
        """When revoked=true and clear=true, memory service is called."""
        mock_mem_svc = AsyncMock()
        mock_mem_svc.remove_trees_by_provider = AsyncMock(return_value=7)

        with (
            patch("app.api.connect.router.get_connect_service") as mock_get_svc,
            patch(
                "app.services.memory.integration_memory.get_integration_memory_service",
                new=AsyncMock(return_value=mock_mem_svc),
            ),
        ):
            mock_service = MagicMock()
            mock_service.revoke.return_value = True
            mock_get_svc.return_value = mock_service

            response = client.post(
                f"{API_PREFIX}/connect/revoke",
                json={"profile_id": "cursor", "clear_synced_memory": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["revoked"] is True
            assert data["trees_removed"] == 7
            mock_mem_svc.remove_trees_by_provider.assert_called_once_with("cursor")

    def test_revoke_clear_but_service_none(self, client: TestClient):
        """When memory service not initialized, gracefully returns 0."""
        with (
            patch("app.api.connect.router.get_connect_service") as mock_get_svc,
            patch(
                "app.services.memory.integration_memory.get_integration_memory_service",
                new=AsyncMock(return_value=None),
            ),
        ):
            mock_service = MagicMock()
            mock_service.revoke.return_value = True
            mock_get_svc.return_value = mock_service

            response = client.post(
                f"{API_PREFIX}/connect/revoke",
                json={"profile_id": "cursor", "clear_synced_memory": True},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["revoked"] is True
            assert data["trees_removed"] == 0
