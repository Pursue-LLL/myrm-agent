"""HTTP integration tests for GET /api/v1/integrations/mcp/registry/search."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestMCPRegistrySearchEndpoint:
    """Live proxy to Smithery — validates api.smithery.ai wiring (no httpx mock)."""

    def test_registry_search_returns_servers(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/integrations/mcp/registry/search",
            params={"page": 1, "page_size": 5},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert isinstance(data["servers"], list)
        assert len(data["servers"]) >= 1
        first = data["servers"][0]
        assert first.get("qualifiedName")
        assert data.get("totalPages", 0) >= 1
