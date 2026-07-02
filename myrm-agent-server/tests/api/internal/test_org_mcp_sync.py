"""Unit tests for CP org MCP sync endpoint stdio filtering."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.internal.org_mcp_sync import router as org_mcp_sync_router


@pytest.fixture
def org_mcp_sync_app() -> FastAPI:
    app = FastAPI()
    app.include_router(org_mcp_sync_router)
    return app


@pytest.mark.asyncio
async def test_org_mcp_sync_filters_stdio_when_disabled(org_mcp_sync_app: FastAPI) -> None:
    transport = ASGITransport(app=org_mcp_sync_app)

    with patch("app.api.internal.org_mcp_sync.settings") as mock_settings:
        mock_settings.mcp.allow_stdio = False
        with patch(
            "app.api.internal.org_mcp_sync.ConfigService",
        ) as mock_config_cls:
            mock_config = AsyncMock()
            mock_config_cls.return_value = mock_config

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/admin/org-mcp-sync",
                    json={
                        "mcp_servers": [
                            {"id": "1", "name": "sse-one", "type": "sse", "url": "https://a/sse"},
                            {"id": "2", "name": "stdio-two", "type": "stdio", "command": "npx"},
                        ]
                    },
                )

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    saved_value = mock_config.set.await_args.kwargs["value"]
    assert len(saved_value["servers"]) == 1
    assert saved_value["servers"][0]["type"] == "sse"
