"""Tests for Jina and Firecrawl escalation providers (httpx mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult

from app.services.web_fetch.providers.firecrawl import FirecrawlEscalationProvider
from app.services.web_fetch.providers.jina import JinaEscalationProvider


@pytest.mark.asyncio
async def test_jina_provider_success() -> None:
    provider = JinaEscalationProvider(api_key="jina-key")
    mock_response = MagicMock()
    mock_response.text = "# Title\n\nBody content"
    mock_response.raise_for_status = MagicMock()

    with patch(
        "app.services.web_fetch.providers.jina.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=True)),
    ):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch_url("https://example.com")

    assert result is not None
    assert result.content == "Body content"
    assert result.title == "Title"
    assert result.provider_id == "jina"


@pytest.mark.asyncio
async def test_jina_provider_blocked_by_ssrf() -> None:
    provider = JinaEscalationProvider()
    with patch(
        "app.services.web_fetch.providers.jina.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=False, error="blocked")),
    ):
        assert await provider.fetch_url("https://127.0.0.1") is None


@pytest.mark.asyncio
async def test_jina_provider_http_error() -> None:
    provider = JinaEscalationProvider()
    with patch(
        "app.services.web_fetch.providers.jina.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=True)),
    ):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
            mock_client_cls.return_value = mock_client

            assert await provider.fetch_url("https://example.com") is None


@pytest.mark.asyncio
async def test_firecrawl_provider_success() -> None:
    provider = FirecrawlEscalationProvider("fc-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {"markdown": "# Page\n\nText", "metadata": {"title": "Page"}, "url": "https://example.com"}
    }
    mock_response.raise_for_status = MagicMock()

    with patch(
        "app.services.web_fetch.providers.firecrawl.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=True)),
    ):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch_url("https://example.com")

    assert result is not None
    assert "Text" in result.content
    assert result.title == "Page"


def test_firecrawl_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        FirecrawlEscalationProvider("  ")


@pytest.mark.asyncio
async def test_firecrawl_provider_ssrf_blocked() -> None:
    provider = FirecrawlEscalationProvider("fc-key")
    with patch(
        "app.services.web_fetch.providers.firecrawl.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=False, error="blocked")),
    ):
        assert await provider.fetch_url("https://127.0.0.1") is None


@pytest.mark.asyncio
async def test_firecrawl_provider_http_error() -> None:
    provider = FirecrawlEscalationProvider("fc-key")
    with patch(
        "app.services.web_fetch.providers.firecrawl.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=True)),
    ):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("fail"))
            mock_client_cls.return_value = mock_client

            assert await provider.fetch_url("https://example.com") is None


@pytest.mark.asyncio
async def test_jina_truncates_when_max_chars_set() -> None:
    provider = JinaEscalationProvider()
    mock_response = MagicMock()
    mock_response.text = "x" * 100
    mock_response.raise_for_status = MagicMock()

    with patch(
        "app.services.web_fetch.providers.jina.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=True)),
    ):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await provider.fetch_url("https://example.com", max_chars=10)

    assert result is not None
    assert len(result.content) == 10


@pytest.mark.asyncio
async def test_firecrawl_provider_empty_markdown() -> None:
    provider = FirecrawlEscalationProvider("fc-key")
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"markdown": ""}}
    mock_response.raise_for_status = MagicMock()

    with patch(
        "app.services.web_fetch.providers.firecrawl.async_validate_url_for_ssrf",
        new=AsyncMock(return_value=SSRFResult(safe=True)),
    ):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            assert await provider.fetch_url("https://example.com") is None
