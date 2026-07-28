"""Tests for x_search_provider is_degraded field."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai_agents.general_agent.tools.x_search_provider import XSearchProvider, XSearchProviderConfig


@pytest.fixture
def xai_config() -> XSearchProviderConfig:
    return XSearchProviderConfig(api_key="test-key", base_url="https://api.x.ai/v1")


@pytest.mark.asyncio
async def test_search_result_is_degraded_when_filters_and_no_citations(xai_config: XSearchProviderConfig) -> None:
    """is_degraded=True when filters are used but no citations returned."""
    from unittest.mock import MagicMock

    import httpx

    mock_response_data = {
        "output_text": "Based on my knowledge, the topic is...",
        "output": [],
        "citations": [],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    provider = XSearchProvider(xai_config)
    provider._client = mock_client

    result = await provider.search(
        query="test query",
        allowed_handles=["elonmusk"],
    )

    assert result.is_degraded is True
    assert "No matching posts found" in result.snippet


@pytest.mark.asyncio
async def test_search_result_not_degraded_when_citations_exist(xai_config: XSearchProviderConfig) -> None:
    """is_degraded=False when citations are present."""
    from unittest.mock import MagicMock

    import httpx

    mock_response_data = {
        "output_text": "According to @user, ...",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "text",
                        "text": "According to @user, ...",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://x.com/user/status/123",
                                "title": "Tweet",
                            }
                        ],
                    }
                ],
            }
        ],
        "citations": [],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    provider = XSearchProvider(xai_config)
    provider._client = mock_client

    result = await provider.search(
        query="test query",
        allowed_handles=["user"],
    )

    assert result.is_degraded is False


@pytest.mark.asyncio
async def test_search_result_not_degraded_when_no_filters(xai_config: XSearchProviderConfig) -> None:
    """is_degraded=False when no filters are used, even without citations."""
    from unittest.mock import MagicMock

    import httpx

    mock_response_data = {
        "output_text": "General answer about the topic...",
        "output": [],
        "citations": [],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    provider = XSearchProvider(xai_config)
    provider._client = mock_client

    result = await provider.search(query="general topic")

    assert result.is_degraded is False
