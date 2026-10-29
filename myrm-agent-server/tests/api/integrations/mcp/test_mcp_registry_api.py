"""HTTP tests for the MCP registry proxy: GET /api/v1/integrations/mcp/registry/{search,detail}."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.integrations.mcp_registry import (
    RegistryEnvVar,
    RegistrySearchResult,
    RegistryServer,
    RegistryServerDetail,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_SEARCH_URL = "/api/v1/integrations/mcp/registry/search"
_DETAIL_URL = "/api/v1/integrations/mcp/registry/detail"
_GET_REGISTRY = "app.services.integrations.mcp_registry.get_mcp_registry"


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
            _SEARCH_URL,
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

    def test_registry_detail_namespaced_server(self, client: TestClient) -> None:
        response = client.get(f"{_DETAIL_URL}/vercel/grep")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data.get("qualifiedName") == "vercel/grep"
        assert data.get("transportType")


class _StubRegistry:
    """Registry double returning real service DTOs (or failing), recording how the endpoint calls it."""

    def __init__(
        self,
        *,
        search_result: RegistrySearchResult | None = None,
        detail: RegistryServerDetail | None = None,
        error: Exception | None = None,
    ) -> None:
        self._search_result = search_result
        self._detail = detail
        self._error = error
        self.search_calls: list[tuple[str, int, int]] = []
        self.detail_calls: list[str] = []

    async def search(self, *, query: str, page: int, page_size: int) -> RegistrySearchResult:
        self.search_calls.append((query, page, page_size))
        if self._error is not None:
            raise self._error
        assert self._search_result is not None
        return self._search_result

    async def get_detail(self, qualified_name: str) -> RegistryServerDetail:
        self.detail_calls.append(qualified_name)
        if self._error is not None:
            raise self._error
        assert self._detail is not None
        return self._detail


class TestMCPRegistryProxyMapping:
    """Deterministic proxy behaviour against a stub registry: DTO mapping and upstream failure handling."""

    def test_search_forwards_the_query_and_maps_servers(self, client: TestClient) -> None:
        registry = _StubRegistry(
            search_result=RegistrySearchResult(
                servers=[
                    RegistryServer(
                        qualified_name="acme/git",
                        display_name="Git",
                        description="Git tools",
                        icon_url="https://cdn.example.com/git.png",
                        homepage="https://example.com/git",
                        use_count=42,
                    ),
                    RegistryServer(qualified_name="acme/bare", display_name="Bare"),
                ],
                page=2,
                page_size=7,
                total_pages=9,
            )
        )

        with patch(_GET_REGISTRY, return_value=registry):
            response = client.get(_SEARCH_URL, params={"q": "git", "page": 2, "page_size": 7})

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert registry.search_calls == [("git", 2, 7)]
        assert (data["page"], data["pageSize"], data["totalPages"]) == (2, 7, 9)
        assert data["servers"][0] == {
            "qualifiedName": "acme/git",
            "displayName": "Git",
            "description": "Git tools",
            "iconUrl": "https://cdn.example.com/git.png",
            "homepage": "https://example.com/git",
            "useCount": 42,
        }
        assert data["servers"][1]["iconUrl"] is None
        assert data["servers"][1]["useCount"] == 0

    def test_search_upstream_failure_returns_502_with_the_cause(self, client: TestClient) -> None:
        registry = _StubRegistry(error=RuntimeError("upstream down"))

        with patch(_GET_REGISTRY, return_value=registry):
            response = client.get(_SEARCH_URL)

        assert response.status_code == 502
        assert "Search failed: upstream down" in response.json()["detail"]["message"]

    def test_detail_resolves_namespaced_names_and_maps_env_vars(self, client: TestClient) -> None:
        registry = _StubRegistry(
            detail=RegistryServerDetail(
                qualified_name="vercel/grep",
                display_name="Grep",
                description="Code search",
                transport_type="streamable_http",
                env_vars=[
                    RegistryEnvVar(name="GREP_TOKEN", description="API token", required=True),
                    RegistryEnvVar(name="GREP_REGION"),
                ],
            )
        )

        with patch(_GET_REGISTRY, return_value=registry):
            response = client.get(f"{_DETAIL_URL}/vercel/grep")

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert registry.detail_calls == ["vercel/grep"]
        assert data["transportType"] == "streamable_http"
        assert data["envVars"] == [
            {"name": "GREP_TOKEN", "description": "API token", "required": True},
            {"name": "GREP_REGION", "description": "", "required": True},
        ]

    def test_detail_upstream_failure_returns_502_with_the_cause(self, client: TestClient) -> None:
        registry = _StubRegistry(error=LookupError("no such server"))

        with patch(_GET_REGISTRY, return_value=registry):
            response = client.get(f"{_DETAIL_URL}/acme/missing")

        assert response.status_code == 502
        assert "Detail lookup failed: no such server" in response.json()["detail"]["message"]
