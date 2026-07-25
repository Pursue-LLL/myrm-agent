"""Unit tests for x_search_provider.py hardening features.

Covers date validation, retry logic, degraded detection, and citation merging.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.ai_agents.general_agent.tools.x_search_provider import (
    XSearchProvider,
    XSearchProviderConfig,
    _validate_date_range,
)


# ---------------------------------------------------------------------------
# _validate_date_range
# ---------------------------------------------------------------------------

class TestValidateDateRange:
    def test_valid_range(self) -> None:
        assert _validate_date_range("2026-01-01", "2026-01-31") is None

    def test_empty_dates(self) -> None:
        assert _validate_date_range("", "") is None

    def test_single_from_date(self) -> None:
        assert _validate_date_range("2026-01-01", "") is None

    def test_single_to_date(self) -> None:
        assert _validate_date_range("", "2026-12-31") is None

    def test_invalid_format(self) -> None:
        result = _validate_date_range("01-01-2026", "")
        assert result is not None
        assert "YYYY-MM-DD" in result

    def test_invalid_calendar_date(self) -> None:
        result = _validate_date_range("2026-02-30", "")
        assert result is not None

    def test_from_after_to(self) -> None:
        result = _validate_date_range("2026-06-15", "2026-06-01")
        assert result is not None
        assert "on or before" in result

    def test_future_from_date(self) -> None:
        future = "2099-01-01"
        result = _validate_date_range(future, "")
        assert result is not None
        assert "future" in result

    def test_whitespace_trimmed(self) -> None:
        assert _validate_date_range("  2026-01-01  ", "  2026-01-31  ") is None

    def test_same_day_range(self) -> None:
        assert _validate_date_range("2026-07-01", "2026-07-01") is None


# ---------------------------------------------------------------------------
# XSearchProvider.search — retry logic
# ---------------------------------------------------------------------------

def _make_provider() -> XSearchProvider:
    return XSearchProvider(XSearchProviderConfig(api_key="test-key"))


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self) -> None:
        provider = _make_provider()
        mock_response = httpx.Response(
            status_code=401,
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=mock_response.request, response=mock_response,
        ))
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("test query")
        assert result.is_error
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_5xx_then_succeed(self) -> None:
        provider = _make_provider()
        error_response = httpx.Response(
            status_code=502,
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        success_response = httpx.Response(
            status_code=200,
            json={"output_text": "ok", "output": [], "citations": []},
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[
            httpx.HTTPStatusError(
                "Bad Gateway", request=error_response.request, response=error_response,
            ),
            success_response,
        ])
        mock_client.is_closed = False
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.search("test query")

        assert not result.is_error
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout_exhausted(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        mock_client.is_closed = False
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.search("test query")

        assert result.is_error
        assert mock_client.post.call_count == 3  # initial + 2 retries


# ---------------------------------------------------------------------------
# XSearchProvider.search — degraded detection
# ---------------------------------------------------------------------------

class TestDegradedDetection:
    @pytest.mark.asyncio
    async def test_no_warning_without_filters(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={"output_text": "some answer", "output": [], "citations": []},
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("test query")
        assert "general knowledge" not in result.snippet

    @pytest.mark.asyncio
    async def test_warning_with_filter_no_citations(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={"output_text": "some answer", "output": [], "citations": []},
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search(
            "test query", from_date="2026-01-01", to_date="2026-01-31",
        )
        assert "general knowledge" in result.snippet


# ---------------------------------------------------------------------------
# XSearchProvider.search — citation merging
# ---------------------------------------------------------------------------

class TestCitationMerging:
    @pytest.mark.asyncio
    async def test_merges_inline_and_top_level(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={
                "output_text": "answer",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "text",
                                "text": "answer",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://x.com/post/1",
                                        "title": "Inline Post",
                                        "start_index": 0,
                                        "end_index": 6,
                                    },
                                ],
                            },
                        ],
                    },
                ],
                "citations": [
                    {"url": "https://x.com/post/2", "title": "Top Level Post"},
                ],
            },
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("test query")
        urls = [c.url for c in result.citations]
        assert "https://x.com/post/1" in urls
        assert "https://x.com/post/2" in urls
        assert len(result.citations) == 2

    @pytest.mark.asyncio
    async def test_deduplicates_by_url(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={
                "output_text": "answer",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "text",
                                "text": "answer",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://x.com/post/1",
                                        "title": "Post",
                                    },
                                ],
                            },
                        ],
                    },
                ],
                "citations": [
                    {"url": "https://x.com/post/1", "title": "Same Post"},
                ],
            },
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("test query")
        assert len(result.citations) == 1

    @pytest.mark.asyncio
    async def test_top_level_string_citations(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={
                "output_text": "answer",
                "output": [],
                "citations": ["https://x.com/post/1"],
            },
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("test query")
        assert len(result.citations) == 1
        assert result.citations[0].url == "https://x.com/post/1"


# ---------------------------------------------------------------------------
# XSearchProvider.search — date validation integration
# ---------------------------------------------------------------------------

class TestValidateDateRangeEdge:
    def test_to_date_in_future_allowed(self) -> None:
        assert _validate_date_range("2026-01-01", "2099-12-31") is None

    def test_invalid_to_date_format(self) -> None:
        result = _validate_date_range("", "bad-date")
        assert result is not None
        assert "to_date" in result

    def test_only_from_in_future_fails(self) -> None:
        result = _validate_date_range("2099-06-01", "2099-12-31")
        assert result is not None
        assert "future" in result

    def test_month_13_rejected(self) -> None:
        result = _validate_date_range("2026-13-01", "")
        assert result is not None


# ---------------------------------------------------------------------------
# XSearchProvider.search — edge cases
# ---------------------------------------------------------------------------

class TestSearchEdgeCases:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_error(self) -> None:
        provider = XSearchProvider(XSearchProviderConfig(api_key=""))
        result = await provider.search("test")
        assert result.is_error
        assert "not configured" in result.snippet

    @pytest.mark.asyncio
    async def test_allowed_and_excluded_mutual_exclusion(self) -> None:
        provider = _make_provider()
        result = await provider.search(
            "test", allowed_handles=["a"], excluded_handles=["b"],
        )
        assert result.is_error
        assert "cannot be used together" in result.snippet

    @pytest.mark.asyncio
    async def test_handles_exceed_max(self) -> None:
        provider = _make_provider()
        handles = [f"user{i}" for i in range(11)]
        result = await provider.search("test", allowed_handles=handles)
        assert result.is_error
        assert "Maximum" in result.snippet or "10" in result.snippet

    @pytest.mark.asyncio
    async def test_successful_search_full_path(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={
                "output_text": "AI trends in 2026",
                "output": [],
                "citations": [
                    {"url": "https://x.com/post/42", "title": "AI Post"},
                ],
            },
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("AI trends")
        assert not result.is_error
        assert "AI trends" in result.title
        assert result.snippet == "AI trends in 2026"
        assert len(result.citations) == 1

    @pytest.mark.asyncio
    async def test_no_degraded_warning_when_filter_has_citations(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={
                "output_text": "answer",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "text",
                                "text": "answer",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://x.com/1",
                                        "title": "P",
                                    },
                                ],
                            },
                        ],
                    },
                ],
                "citations": [],
            },
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search(
            "test", allowed_handles=["elonmusk"],
        )
        assert "general knowledge" not in result.snippet

    @pytest.mark.asyncio
    async def test_degraded_with_excluded_handles(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={"output_text": "answer", "output": [], "citations": []},
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search(
            "test", excluded_handles=["spambot"],
        )
        assert "general knowledge" in result.snippet

    @pytest.mark.asyncio
    async def test_citations_field_none(self) -> None:
        provider = _make_provider()
        mock_client = AsyncMock()
        mock_response = httpx.Response(
            status_code=200,
            json={"output_text": "answer", "output": []},
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
        )
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.search("test")
        assert not result.is_error
        assert result.citations == []


# ---------------------------------------------------------------------------
# XSearchProvider.search — retry edge: all 5xx retries exhausted
# ---------------------------------------------------------------------------

class TestRetryExhausted:
    @pytest.mark.asyncio
    async def test_all_5xx_retries_exhausted(self) -> None:
        provider = _make_provider()
        error_response = httpx.Response(
            status_code=503,
            request=httpx.Request("POST", "https://api.x.ai/v1/responses"),
            text="Service Unavailable",
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Service Unavailable",
            request=error_response.request,
            response=error_response,
        ))
        mock_client.is_closed = False
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.search("test query")

        assert result.is_error
        assert "503" in result.snippet
        assert mock_client.post.call_count == 3


# ---------------------------------------------------------------------------
# XSearchProvider.search — date validation integration
# ---------------------------------------------------------------------------

class TestDateValidationIntegration:
    @pytest.mark.asyncio
    async def test_invalid_date_returns_error(self) -> None:
        provider = _make_provider()
        result = await provider.search("test", from_date="not-a-date")
        assert result.is_error
        assert "YYYY-MM-DD" in result.snippet

    @pytest.mark.asyncio
    async def test_inverted_range_returns_error(self) -> None:
        provider = _make_provider()
        result = await provider.search(
            "test", from_date="2026-06-15", to_date="2026-06-01",
        )
        assert result.is_error
        assert "on or before" in result.snippet

    @pytest.mark.asyncio
    async def test_future_from_date_returns_error(self) -> None:
        provider = _make_provider()
        result = await provider.search("test", from_date="2099-01-01")
        assert result.is_error
        assert "future" in result.snippet
