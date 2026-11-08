"""web_searcher 多查询并行、搜索缓存、合并请求与凭据隔离测试

测试 WebSearcher.multi_query_parallel_search 以及结果缓存、单飞合并与按凭据隔离的行为
"""

import asyncio
from typing import NoReturn
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing import (
    bucket_search_limit,
    normalize_search_query,
)
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.exceptions import (
    AllQueriesFailedError,
    SearchAPIError,
)
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    WebSearcher,
)


class TestWebSearcherMultiQuery:
    """测试多查询并行搜索"""

    @pytest.mark.asyncio
    async def test_multi_query_parallel(self) -> None:
        """测试并行搜索多个查询"""
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        # Mock搜索服务
        mock_service = AsyncMock()
        mock_service.search = AsyncMock(
            side_effect=[
                [SearchResult(link="https://test1.com", title="R1", snippet="S1")],
                [SearchResult(link="https://test2.com", title="R2", snippet="S2")],
            ]
        )
        searcher._search_service = mock_service

        results = await searcher.multi_query_parallel_search(
            queries=["query1", "query2"],
            results_per_query=5,
        )

        # 返回格式是 [(query, docs, error), ...]
        assert len(results) == 2

        # 解包元组
        query1, docs1, err1 = results[0]
        query2, docs2, err2 = results[1]

        # 验证查询和错误
        assert query1 == "query1"
        assert query2 == "query2"
        assert err1 is None
        assert err2 is None

        # 验证文档列表
        assert len(docs1) == 1
        assert len(docs2) == 1
        assert docs1[0].metadata["url"] == "https://test1.com"
        assert docs2[0].metadata["url"] == "https://test2.com"

    @pytest.mark.asyncio
    async def test_multi_query_empty_list(self) -> None:
        """测试空查询列表"""
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        # 空查询列表应该抛出异常
        with pytest.raises(AllQueriesFailedError, match="no queries were executed"):
            await searcher.multi_query_parallel_search(queries=[], results_per_query=5)

    @pytest.mark.asyncio
    async def test_multi_query_with_exception(self) -> None:
        """测试并行搜索中某个查询失败"""
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        # 使用唯一查询避免缓存
        unique_q1 = f"success_query_{id(searcher)}"
        unique_q2 = f"fail_query_{id(searcher)}"

        # Mock一个成功一个失败
        mock_service = AsyncMock()
        mock_service.search = AsyncMock(
            side_effect=[
                [SearchResult(link="https://test1.com", title="R1", snippet="S1")],
                Exception("Search failed"),
            ]
        )
        searcher._search_service = mock_service

        results = await searcher.multi_query_parallel_search(
            queries=[unique_q1, unique_q2],
            results_per_query=5,
        )

        # 返回格式是 [(query, docs, error), ...]
        assert len(results) == 2
        # 验证有一个成功一个失败
        errors = [r[2] for r in results]
        assert errors.count(None) == 1  # 一个成功
        assert sum(1 for e in errors if e is not None) == 1  # 一个失败


class TestWebSearcherCache:
    """测试搜索缓存"""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_network(self) -> None:
        """Cache hit must skip the network call entirely."""
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        mock_service = AsyncMock()
        mock_results = [SearchResult(link="https://cached.com", title="Cached", snippet="S")]
        mock_service.search = AsyncMock(return_value=mock_results)
        searcher._search_service = mock_service

        unique_query = f"cache_test_query_{id(searcher)}"

        results1 = await searcher.search(unique_query, num_results=5)
        results2 = await searcher.search(unique_query, num_results=5)

        assert results1 == results2
        assert mock_service.search.call_count == 1, "Second call should hit cache, not network"

    @pytest.mark.asyncio
    async def test_cache_miss_different_query(self) -> None:
        """测试不同查询不命中缓存"""
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        mock_service = AsyncMock()
        mock_service.search = AsyncMock(
            side_effect=[
                [SearchResult(link="https://r1.com", title="R1", snippet="S1")],
                [SearchResult(link="https://r2.com", title="R2", snippet="S2")],
            ]
        )
        searcher._search_service = mock_service

        # 使用唯一查询避免全局缓存冲突
        unique_q1 = f"unique_query_1_{id(searcher)}"
        unique_q2 = f"unique_query_2_{id(searcher)}"

        await searcher.search(unique_q1)
        await searcher.search(unique_q2)

        # 应该调用两次API
        assert mock_service.search.call_count == 2


class TestSearchLimitBucketing:
    """Limit bucketing helpers"""

    def test_bucket_search_limit_rounds_up(self) -> None:
        assert bucket_search_limit(1) == 10
        assert bucket_search_limit(5) == 10
        assert bucket_search_limit(10) == 10
        assert bucket_search_limit(11) == 20
        assert bucket_search_limit(100) == 100
        assert bucket_search_limit(200) == 100

    def test_normalize_search_query(self) -> None:
        assert normalize_search_query("  Hello   World  ") == "hello world"


class TestWebSearcherCoalescing:
    """Single-flight coalescing and limit-bucket cache sharing"""

    @pytest.mark.asyncio
    async def test_concurrent_same_query_single_api_call(self) -> None:
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        call_count = 0

        async def slow_search(query: str, num_results: int, **_kwargs: object) -> list[SearchResult]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return [SearchResult(link=f"https://r{i}.com", title=f"R{i}", snippet=f"S{i}") for i in range(num_results)]

        mock_service = AsyncMock()
        mock_service.search = slow_search
        searcher._search_service = mock_service

        unique_query = f"coalesce_query_{id(searcher)}"
        results = await asyncio.gather(
            searcher.search(unique_query, num_results=5),
            searcher.search(unique_query, num_results=5),
            searcher.search(unique_query, num_results=5),
        )

        assert call_count == 1
        assert all(len(r) == 5 for r in results)

    @pytest.mark.asyncio
    async def test_limit_bucket_shares_cache_and_slices(self) -> None:
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        mock_results = [SearchResult(link=f"https://r{i}.com", title=f"R{i}", snippet=f"S{i}") for i in range(10)]
        mock_service = AsyncMock()
        mock_service.search = AsyncMock(return_value=mock_results)
        searcher._search_service = mock_service

        unique_query = f"bucket_query_{id(searcher)}"
        small = await searcher.search(unique_query, num_results=5)
        large = await searcher.search(unique_query, num_results=8)

        assert mock_service.search.call_count == 1
        assert len(small) == 5
        assert len(large) == 8
        assert small[0].link == "https://r0.com"
        assert large[7].link == "https://r7.com"

    @pytest.mark.asyncio
    async def test_query_normalization_shares_cache(self) -> None:
        config = SearchServiceConfig(search_service="tavily", api_key="test_key")
        searcher = WebSearcher(config)

        mock_results = [SearchResult(link="https://r0.com", title="R0", snippet="S0")]
        mock_service = AsyncMock()
        mock_service.search = AsyncMock(return_value=mock_results)
        searcher._search_service = mock_service

        base = f"norm_query_{id(searcher)}"
        await searcher.search(f"  {base.upper()}  ", num_results=5)
        await searcher.search(base, num_results=5)

        assert mock_service.search.call_count == 1

    @pytest.mark.asyncio
    async def test_coalescing_propagates_leader_failure(self) -> None:
        config = SearchServiceConfig(search_service="tavily", api_key="test_key", search_max_retries=0)
        searcher = WebSearcher(config)

        call_count = 0

        async def failing_search(*_args: object, **_kwargs: object) -> NoReturn:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.02)
            raise RuntimeError("provider down")

        mock_service = AsyncMock()
        mock_service.search = failing_search
        searcher._search_service = mock_service

        unique_query = f"fail_coalesce_{id(searcher)}"
        outcomes = await asyncio.gather(
            searcher.search(unique_query, num_results=5),
            searcher.search(unique_query, num_results=5),
            return_exceptions=True,
        )

        assert call_count == 1
        assert all(isinstance(o, SearchAPIError) for o in outcomes)


class TestResultCacheCredentialScope:
    """A cached payload belongs to the credential that produced it."""

    @pytest.mark.asyncio
    async def test_rotated_api_key_does_not_replay_the_old_payload(self) -> None:
        counted = AsyncMock()
        counted.search = AsyncMock(return_value=[SearchResult(title="T", link="https://ok.com", snippet="S")])

        with patch.object(WebSearcher, "_get_search_service", AsyncMock(return_value=counted)):
            await WebSearcher(SearchServiceConfig(search_service="tavily", api_key="old-key")).search("same query", 5)
            await WebSearcher(SearchServiceConfig(search_service="tavily", api_key="new-key")).search("same query", 5)
            # Same credential keeps hitting the cache: the key change is the only variable.
            await WebSearcher(SearchServiceConfig(search_service="tavily", api_key="new-key")).search("same query", 5)

        assert counted.search.await_count == 2

    @pytest.mark.asyncio
    async def test_searxng_ignores_gateway_routing_when_scoping_the_cache(self) -> None:
        """SearxNG is always reached directly, so its own endpoint is its identity, not the gateway's."""
        counted = AsyncMock()
        counted.search = AsyncMock(return_value=[SearchResult(title="T", link="https://ok.com", snippet="S")])
        gateway = ToolGatewayConfig(
            use_gateway=True, gateway_url="https://gw.example/tool-relay", auth_token="vk-shared"
        )

        with patch.object(WebSearcher, "_get_search_service", AsyncMock(return_value=counted)):
            await WebSearcher(
                SearchServiceConfig(search_service="searxng", api_base="http://localhost:8081", gateway_config=gateway)
            ).search("same query", 5)
            await WebSearcher(
                SearchServiceConfig(search_service="searxng", api_base="http://localhost:9999", gateway_config=gateway)
            ).search("same query", 5)

        assert counted.search.await_count == 2

    @pytest.mark.asyncio
    async def test_gateway_byok_fallback_scopes_the_cache_to_the_direct_key(self) -> None:
        """A routed config that keeps its own provider key can fall back to it mid-request, so that key scopes too."""
        counted = AsyncMock()
        counted.search = AsyncMock(return_value=[SearchResult(title="T", link="https://ok.com", snippet="S")])
        gateway = ToolGatewayConfig(
            use_gateway=True, gateway_url="https://gw.example/tool-relay", auth_token="vk-shared"
        )

        with patch.object(WebSearcher, "_get_search_service", AsyncMock(return_value=counted)):
            await WebSearcher(
                SearchServiceConfig(search_service="tavily", api_key="account-a", gateway_config=gateway)
            ).search("same query", 5)
            await WebSearcher(
                SearchServiceConfig(search_service="tavily", api_key="account-b", gateway_config=gateway)
            ).search("same query", 5)

        assert counted.search.await_count == 2
