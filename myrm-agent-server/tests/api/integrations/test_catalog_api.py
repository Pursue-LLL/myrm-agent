"""Tests for Integration Catalog API endpoints.

Tests cover:
- GET /integrations/catalog (list all, search, category filter)
- GET /integrations/catalog/{entry_id} (single entry, 404)
- Response schema validation
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestCatalogListEndpoint:
    """Tests for GET /api/v1/integrations/catalog."""

    def test_list_all(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        payload = data["data"]
        assert payload["total"] >= 14
        assert len(payload["entries"]) >= 14
        assert len(payload["categories"]) == 9

    def test_list_with_category_filter(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog?category=development")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] >= 3
        assert all(e["category"] == "development" for e in data["entries"])

    def test_list_with_search_query(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog?q=notion")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["entries"][0]["id"] == "notion"

    def test_list_search_no_results(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog?q=xyznonexistent")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["entries"] == []

    def test_list_empty_category(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog?category=nonexistent")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0

    def test_response_schema(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog")
        data = response.json()["data"]
        entry = data["entries"][0]
        required_fields = [
            "id",
            "name",
            "nameZh",
            "description",
            "descriptionZh",
            "icon",
            "category",
            "connectorType",
            "authType",
            "tags",
        ]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"


class TestCatalogDetailEndpoint:
    """Tests for GET /api/v1/integrations/catalog/{entry_id}."""

    def test_get_existing_entry(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/github")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == "github"
        assert data["name"] == "GitHub"
        assert data["connectorType"] == "mcp"
        assert data["authType"] == "api_key"
        assert data["mcpConfig"] is not None

    def test_get_entry_with_mcp_config(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/notion")
        data = response.json()["data"]
        mcp = data["mcpConfig"]
        assert mcp is not None
        assert mcp["name"] == "notion"
        assert mcp["type"] == "stdio"
        assert "args" in mcp

    def test_get_nonexistent_entry(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/does_not_exist")
        assert response.status_code == 404

    def test_entry_has_help_url(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/notion")
        data = response.json()["data"]
        assert data["helpUrl"] is not None
        assert "notion.so" in data["helpUrl"]

    def test_entry_env_key_present(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/github")
        data = response.json()["data"]
        assert data["envKey"] is not None

    def test_feishu_entry_has_credential_fields(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/feishu")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == "feishu"
        assert data["connectorType"] == "mcp"
        fields = data["credentialFields"]
        assert fields is not None
        assert len(fields) == 2
        keys = [f["key"] for f in fields]
        assert "{{app_id}}" in keys
        assert "{{app_secret}}" in keys

    def test_dingtalk_entry_has_credential_fields(self, client: TestClient) -> None:
        response = client.get("/api/v1/integrations/catalog/dingtalk")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == "dingtalk"
        fields = data["credentialFields"]
        assert fields is not None
        assert len(fields) == 2
        mcp = data["mcpConfig"]
        assert mcp is not None
        assert "env" in mcp
        assert mcp["env"]["ACTIVE_PROFILES"] is not None
