"""web_search 错误处理和边缘情况测试

测试未覆盖的关键错误处理路径和边缘情况
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.error_handling import (
    build_search_error_context,
    is_retryable_search_error,
)
from myrm_agent_harness.toolkits.web_search.core.exceptions import (
    SearchAPIError,
)
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    WebSearcher,
)

from ._fakes import FakeAPIConnectionError, FakeProviderHTTPError


class TestErrorClassification:
    """测试错误分类逻辑"""

    def test_retryable_timeout_errors(self) -> None:
        """测试超时错误可重试"""
        assert is_retryable_search_error(TimeoutError())
        assert is_retryable_search_error(TimeoutError())

    def test_retryable_connection_errors(self) -> None:
        """测试连接错误可重试"""
        assert is_retryable_search_error(ConnectionError("Connection failed"))
        assert is_retryable_search_error(OSError("Network error"))

    def test_retryable_status_codes(self) -> None:
        """测试可重试的HTTP状态码"""
        for code in [408, 425, 500, 502, 503, 504]:
            exc = FakeProviderHTTPError(status_code=code)
            assert is_retryable_search_error(exc), f"Status {code} should be retryable"

    def test_quota_status_code_not_retryable(self) -> None:
        """429 / quota should not retry on the same provider hop."""
        exc = FakeProviderHTTPError(status_code=429)
        assert not is_retryable_search_error(exc)

    def test_non_retryable_status_codes(self) -> None:
        """测试不可重试的HTTP状态码"""
        for code in [400, 401, 403, 404, 405, 422]:
            exc = FakeProviderHTTPError(status_code=code)
            assert not is_retryable_search_error(exc), f"Status {code} should not be retryable"

    def test_retryable_error_messages(self) -> None:
        """测试通过错误消息判断可重试"""
        test_cases = [
            "502 Bad Gateway",
            "Connection timeout",
            "Server timed out",
            "Connection refused",
            "Broken pipe error",
        ]
        for msg in test_cases:
            assert is_retryable_search_error(Exception(msg)), f"Message '{msg}' should be retryable"

    def test_http_status_attribute(self) -> None:
        """测试 http_status 属性"""
        exc = FakeProviderHTTPError(http_status=503)
        assert is_retryable_search_error(exc)

    def test_quota_exceeded_not_retryable(self) -> None:
        """配额超限不可重试（即使 status=500）"""
        exc = FakeAPIConnectionError(
            'TavilyException - {"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )
        assert not is_retryable_search_error(exc)

    def test_invalid_api_key_not_retryable(self) -> None:
        """无效 API key 不可重试"""
        exc = FakeAPIConnectionError('TavilyException - {"detail":{"error":"Invalid API key"}}')
        assert not is_retryable_search_error(exc)

    def test_real_connection_refused_still_retryable(self) -> None:
        """真实连接拒绝仍可重试"""
        assert is_retryable_search_error(ConnectionError("Connection refused"))

    def test_apiconnectionerror_wrapper_not_matched_as_connection_error(self) -> None:
        """LiteLLM APIConnectionError 包装器不应被当作真实连接错误"""
        exc = FakeAPIConnectionError("Something went wrong with the provider")
        # status=500 makes it retryable, but not because of "connection" keyword
        assert is_retryable_search_error(exc)  # retryable due to status=500


class TestErrorContext:
    """测试错误上下文构建"""

    def test_build_context_with_status_code(self) -> None:
        """测试带状态码的上下文"""
        exc = FakeProviderHTTPError("API error", status_code=429)

        ctx = build_search_error_context(
            exc,
            query="test query",
            provider="tavily",
            attempt_index=0,
        )

        assert ctx.query == "test query"
        assert ctx.status_code == 429
        assert ctx.retryable is False
        assert ctx.metadata["provider"] == "tavily"
        assert ctx.metadata["attempt_index"] == "0"

    def test_build_context_with_response_body(self) -> None:
        """测试带响应体的上下文"""
        exc = FakeProviderHTTPError(status_code=400, response="Invalid request: missing field 'query'")

        ctx = build_search_error_context(
            exc,
            query="test",
            provider="searxng",
            attempt_index=1,
            error_code="ValidationError",
        )

        assert ctx.response_body == "Invalid request: missing field 'query'"
        assert ctx.error_code == "ValidationError"
        assert ctx.retryable is False

    def test_build_context_with_body_attribute(self) -> None:
        """测试 body 属性"""
        exc = FakeProviderHTTPError(body="Error body content")

        ctx = build_search_error_context(
            exc,
            query="test",
            provider="test",
            attempt_index=0,
        )

        assert ctx.response_body == "Error body content"


class TestTimeoutHandling:
    """测试超时处理"""

    @pytest.mark.asyncio
    async def test_search_and_process_timeout(self) -> None:
        """测试 search_and_process 超时错误处理"""
        config = SearchServiceConfig(
            search_service="tavily",
            api_key="test_key",
        )
        searcher = WebSearcher(config)

        with patch.object(
            searcher,
            "search",
            side_effect=TimeoutError("Search timeout"),
        ):
            query, docs, error = await searcher.search_and_process("test", 5)

            assert query == "test"
            assert docs == []
            assert error is not None
            assert isinstance(error, SearchAPIError)
            assert "time budget" in error.message
            assert error.context.retryable is True
            assert error.context.error_code == "TimeoutError"


class TestLiteLLMSearchEdgeCases:
    """测试 LiteLLMSearch 边缘情况"""

    def test_result_parsing_with_all_fields(self) -> None:
        """测试带完整字段的结果解析"""
        mock_result = Mock()
        mock_result.title = "Test Article"
        mock_result.url = "https://example.com"
        mock_result.snippet = "Test snippet"
        mock_result.date = "2024-03-19"

        result_dict = {
            "title": mock_result.title if hasattr(mock_result, "title") else "",
            "link": mock_result.url if hasattr(mock_result, "url") else "",
            "snippet": mock_result.snippet if hasattr(mock_result, "snippet") else "",
        }
        if hasattr(mock_result, "date") and mock_result.date:
            result_dict["date"] = mock_result.date

        result = SearchResult.from_dict(result_dict)
        assert result.title == "Test Article"
        assert result.link == "https://example.com"
        assert result.date == "2024-03-19"

    def test_result_parsing_with_missing_attributes(self) -> None:
        """测试缺少属性的结果解析"""
        mock_result = Mock(spec=[])  # Empty spec, no attributes

        result_dict = {
            "title": mock_result.title if hasattr(mock_result, "title") else "",
            "link": mock_result.url if hasattr(mock_result, "url") else "",
            "snippet": mock_result.snippet if hasattr(mock_result, "snippet") else "",
        }

        result = SearchResult.from_dict(result_dict)
        assert result.title == "Untitled"
        assert result.link == ""
        assert result.snippet == ""


class TestExtractKeyError:
    """测试 _extract_key_error 语义优先错误提取"""

    @pytest.fixture()
    def searcher(self) -> WebSearcher:
        config = SearchServiceConfig(search_service="tavily", api_key="test")
        return WebSearcher(config)

    def test_quota_exceeded(self, searcher: WebSearcher) -> None:
        exc = FakeAPIConnectionError(
            'TavilyException - {"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )
        msg = searcher._extract_key_error(exc)
        assert "quota exceeded" in msg.lower()

    def test_invalid_api_key(self, searcher: WebSearcher) -> None:
        exc = FakeAPIConnectionError('TavilyException - {"detail":{"error":"Invalid API key"}}')
        msg = searcher._extract_key_error(exc)
        assert "invalid api key" in msg.lower()

    def test_real_connection_refused(self, searcher: WebSearcher) -> None:
        exc = ConnectionError("Connection refused")
        msg = searcher._extract_key_error(exc)
        assert msg == "Cannot connect to search service"

    def test_rate_limit(self, searcher: WebSearcher) -> None:
        exc = Exception("Rate limit exceeded")
        msg = searcher._extract_key_error(exc)
        assert "rate limit" in msg.lower()

    def test_http_401(self, searcher: WebSearcher) -> None:
        exc = Exception("401 Unauthorized")
        msg = searcher._extract_key_error(exc)
        assert "authentication failed" in msg.lower()

    def test_fallback_to_default(self, searcher: WebSearcher) -> None:
        exc = Exception("Some unknown error happened")
        msg = searcher._extract_key_error(exc)
        assert "Exception:" in msg

    def test_apiconnectionerror_not_matched_as_connection_error(self, searcher: WebSearcher) -> None:
        """APIConnectionError 包装的未知错误不应返回 'Cannot connect'"""
        exc = FakeAPIConnectionError("Something went wrong")
        msg = searcher._extract_key_error(exc)
        assert msg != "Cannot connect to search service"


class TestWebSearcherCacheLogLevel:
    """测试缓存日志级别"""

    @pytest.mark.asyncio
    async def test_cache_hit_uses_info_level(self) -> None:
        """测试缓存命中使用 INFO 级别日志"""
        config = SearchServiceConfig(
            search_service="tavily",
            api_key="test_key",
        )
        searcher = WebSearcher(config)

        mock_service = AsyncMock()
        mock_service.search.return_value = [
            SearchResult(
                title="Test",
                link="https://example.com",
                snippet="Test snippet",
            )
        ]

        with patch.object(searcher, "_get_search_service", return_value=mock_service):
            await searcher.search("test query", 5)

        with patch("myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing.logger") as mock_logger:
            result = await searcher.search("test query", 5)

            assert len(result) == 1
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            assert "cache hit" in call_args.lower() or "Search cache hit" in call_args
