"""HTTP tests for GET /api/v1/integrations/mcp/resource (MCP App UI resource proxy)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_RESOURCE_URL = "/api/v1/integrations/mcp/resource"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app, raise_server_exceptions=False)


class TestMCPResourceEndpoint:
    @pytest.fixture
    def pool(self) -> Iterator[MagicMock]:
        """Install a fake connection pool whose connections the test populates."""
        manager = MagicMock()
        manager._connections = {}
        previous = MCPConnectionManager._instance
        MCPConnectionManager._instance = manager
        try:
            yield manager
        finally:
            MCPConnectionManager._instance = previous

    @staticmethod
    def _read(client: TestClient, path: str = "a.html") -> Response:
        return client.get(f"{_RESOURCE_URL}?uri=ui://s/{path}&server=s")

    @staticmethod
    def _conn(**read_resource: object) -> MagicMock:
        conn = MagicMock()
        conn.read_resource = AsyncMock(**read_resource)
        return conn

    def test_pool_not_initialized_returns_502(self, client: TestClient) -> None:
        previous = MCPConnectionManager._instance
        MCPConnectionManager._instance = None
        try:
            response = self._read(client)
        finally:
            MCPConnectionManager._instance = previous

        assert response.status_code == 502

    def test_no_active_connections_returns_502(self, client: TestClient, pool: MagicMock) -> None:
        assert self._read(client).status_code == 502

    @pytest.mark.parametrize(
        ("extension", "mime_type"),
        [(".js", "application/javascript"), (".css", "text/css"), (".json", "application/json")],
    )
    def test_resource_mime_type_follows_the_extension(
        self,
        client: TestClient,
        pool: MagicMock,
        extension: str,
        mime_type: str,
    ) -> None:
        pool._connections = {"h1": self._conn(return_value=b"console.log(1)")}

        response = self._read(client, f"file{extension}")

        assert response.status_code == 200
        assert response.json()["data"]["mime_type"] == mime_type

    def test_runtime_error_from_every_connection_returns_502(self, client: TestClient, pool: MagicMock) -> None:
        pool._connections = {"h1": self._conn(side_effect=RuntimeError("missing"))}

        response = self._read(client)

        assert response.status_code == 502
        assert "missing" in response.text

    def test_timeout_returns_408(self, client: TestClient, pool: MagicMock) -> None:
        pool._connections = {"h1": self._conn(side_effect=asyncio.TimeoutError())}

        assert self._read(client).status_code == 408

    def test_unexpected_error_falls_through_to_the_next_connection(self, client: TestClient, pool: MagicMock) -> None:
        broken = self._conn(side_effect=ValueError("corrupt pipe"))
        healthy = self._conn(return_value=b"<p>ok</p>")
        pool._connections = {"h1": broken, "h2": healthy}

        response = self._read(client)

        assert response.status_code == 200, response.text
        broken.read_resource.assert_awaited_once()
        healthy.read_resource.assert_awaited_once()

    def test_unexpected_error_on_every_connection_reports_the_last_cause(
        self,
        client: TestClient,
        pool: MagicMock,
    ) -> None:
        pool._connections = {"h1": self._conn(side_effect=ValueError("corrupt pipe"))}

        response = self._read(client)

        assert response.status_code == 502
        assert "corrupt pipe" in response.text
