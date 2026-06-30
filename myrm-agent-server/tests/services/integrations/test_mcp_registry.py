"""Unit tests for Smithery MCP registry proxy."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.integrations.mcp_registry import MCPRegistryService


@pytest.mark.asyncio
async def test_search_parses_smithery_pagination_envelope() -> None:
    service = MCPRegistryService()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "servers": [
            {
                "qualifiedName": "exa",
                "displayName": "Exa Search",
                "description": "Web search",
                "iconUrl": "https://example.com/icon.png",
                "homepage": "https://exa.ai",
                "useCount": 100,
            }
        ],
        "pagination": {"currentPage": 2, "pageSize": 10, "totalPages": 5, "totalCount": 50},
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch.object(service, "_get_client", return_value=mock_client):
        result = await service.search(query="search", page=2, page_size=10)

    assert result.page == 2
    assert result.page_size == 10
    assert result.total_pages == 5
    assert len(result.servers) == 1
    assert result.servers[0].qualified_name == "exa"
    mock_client.get.assert_awaited_once()
    call_url = mock_client.get.await_args.args[0]
    assert call_url == "https://api.smithery.ai/servers"
