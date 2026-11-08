"""provider chain 故障转移的错误路径测试

覆盖额度耗尽、无效密钥、全部失败、供应商故障不拉黑、按序尝试与跳上结果缓存
"""

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.exceptions import (
    AllQueriesFailedError,
    SearchAPIError,
)
from myrm_agent_harness.toolkits.web_search.providers.search_service_factory import SearchService
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    WebSearcher,
)

from ._fakes import FakeAPIConnectionError


class TestProviderChain:
    """测试 priority provider chain 故障转移"""

    def setup_method(self) -> None:
        from myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing import (
            reset_search_coalescing_state_for_tests,
        )
        from myrm_agent_harness.toolkits.web_search.providers.chain import (
            default_quota_tracker,
        )

        reset_search_coalescing_state_for_tests()
        # The quota tracker is a process-wide singleton: a provider left depleted by a sibling test would be skipped
        # by these chains, so every test starts from, and leaves behind, a clean tracker.
        default_quota_tracker.reset_all()

    def teardown_method(self) -> None:
        from myrm_agent_harness.toolkits.web_search.providers.chain import (
            default_quota_tracker,
        )

        default_quota_tracker.reset_all()

    def _chain_config(self, *hops: SearchServiceConfig) -> SearchServiceConfig:
        head = hops[0]
        return SearchServiceConfig(
            search_service=head.search_service,
            api_key=head.api_key,
            api_base=head.api_base,
            provider_chain=list(hops),
        )

    @pytest.mark.asyncio
    async def test_primary_quota_exceeded_chain_succeeds(self) -> None:
        from myrm_agent_harness.toolkits.web_search.providers.chain import (
            ProviderQuotaStatus,
            default_quota_tracker,
            quota_tracker_key,
        )

        cfg = self._chain_config(
            SearchServiceConfig(search_service="tavily", api_key="tvly-key"),
            SearchServiceConfig(search_service="perplexity", api_key="pplx-key"),
        )
        searcher = WebSearcher(cfg)

        primary_service = AsyncMock()
        primary_service.search.side_effect = FakeAPIConnectionError(
            'TavilyException - {"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )

        fallback_service = AsyncMock()
        fallback_service.search.return_value = [
            SearchResult(title="Fallback", link="https://fallback.com", snippet="Fallback result")
        ]

        async def mock_get_service(instance: WebSearcher, bypass_gateway: bool = False) -> SearchService:
            if instance.config.search_service == "tavily":
                return primary_service
            if instance.config.search_service == "perplexity":
                return fallback_service
            return AsyncMock()

        with patch.object(WebSearcher, "_get_search_service", mock_get_service):
            results = await searcher.search("test", 5)

        assert len(results) == 1
        assert results[0].title == "Fallback"
        # A quota failure is not retried within the hop, and it parks the credential for later searches.
        primary_service.search.assert_awaited_once()
        fallback_service.search.assert_awaited_once()
        scoped_key = quota_tracker_key(SearchServiceConfig(search_service="tavily", api_key="tvly-key"))
        assert default_quota_tracker.get_status(scoped_key)[0] == ProviderQuotaStatus.DEPLETED

    @pytest.mark.asyncio
    async def test_primary_invalid_key_chain_succeeds(self) -> None:
        cfg = self._chain_config(
            SearchServiceConfig(search_service="tavily", api_key="invalid-key"),
            SearchServiceConfig(search_service="searxng", api_base="http://localhost:8081"),
        )
        searcher = WebSearcher(cfg)

        primary_service = AsyncMock()
        primary_service.search.side_effect = FakeAPIConnectionError(
            'TavilyException - {"detail":{"error":"Invalid API key"}}'
        )

        fallback_service = AsyncMock()
        fallback_service.search.return_value = [
            SearchResult(title="SearxNG", link="https://example.com", snippet="SearxNG result")
        ]

        async def mock_get_service(instance: WebSearcher, bypass_gateway: bool = False) -> SearchService:
            if instance.config.search_service == "tavily":
                return primary_service
            if instance.config.search_service == "searxng":
                return fallback_service
            return AsyncMock()

        with patch.object(WebSearcher, "_get_search_service", mock_get_service):
            results = await searcher.search("test", 5)

        assert len(results) == 1
        assert results[0].title == "SearxNG"
        primary_service.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_chain_raises_error(self) -> None:
        primary_cfg = SearchServiceConfig(search_service="tavily", api_key="tvly-key")
        searcher = WebSearcher(primary_cfg)

        primary_service = AsyncMock()
        primary_service.search.side_effect = FakeAPIConnectionError(
            'TavilyException - {"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )

        with (
            patch.object(searcher, "_get_search_service", return_value=primary_service),
            pytest.raises(SearchAPIError, match="quota exceeded"),
        ):
            await searcher.search("test", 5)

    @pytest.mark.asyncio
    async def test_chain_all_fail_raises_error(self) -> None:
        cfg = self._chain_config(
            SearchServiceConfig(search_service="tavily", api_key="tvly-key"),
            SearchServiceConfig(search_service="perplexity", api_key="pplx-key"),
        )
        searcher = WebSearcher(cfg)

        quota_error = FakeAPIConnectionError(
            'TavilyException - {"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )

        service_mock = AsyncMock()
        service_mock.search.side_effect = quota_error

        async def mock_get_service(instance: WebSearcher, bypass_gateway: bool = False) -> SearchService:
            return service_mock

        with patch.object(WebSearcher, "_get_search_service", mock_get_service), pytest.raises(AllQueriesFailedError):
            await searcher.search("test", 5)

        # Quota failures are not retried within a hop: one call per provider, and the chain reached the last one.
        assert service_mock.search.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", ["weather", "how to raise aws service quota", "http 429 meaning"])
    async def test_provider_outage_advances_chain_without_blacklisting(self, query: str) -> None:
        from myrm_agent_harness.toolkits.web_search.providers.chain import (
            ProviderQuotaStatus,
            default_quota_tracker,
            quota_tracker_key,
        )

        cfg = self._chain_config(
            SearchServiceConfig(
                search_service="tavily", api_key="tvly-key", search_max_retries=2, retry_backoff_base_seconds=0.0
            ),
            SearchServiceConfig(search_service="perplexity", api_key="pplx-key"),
        )
        searcher = WebSearcher(cfg)

        primary_service = AsyncMock()
        primary_service.search.side_effect = TimeoutError("Request timed out")
        fallback_service = AsyncMock()
        fallback_service.search.return_value = [
            SearchResult(title="Fallback", link="https://fallback.com", snippet="Fallback result")
        ]

        async def mock_get_service(instance: WebSearcher, bypass_gateway: bool = False) -> SearchService:
            return primary_service if instance.config.search_service == "tavily" else fallback_service

        with patch.object(WebSearcher, "_get_search_service", mock_get_service):
            results = await searcher.search(query, 5)

        assert results[0].title == "Fallback"
        assert primary_service.search.await_count == 3  # the provider's own retries run before the chain hops
        fallback_service.search.assert_awaited_once()
        # An outage, even for a query that mentions quotas or 429, is not a quota event.
        healthy_key = quota_tracker_key(SearchServiceConfig(search_service="tavily", api_key="tvly-key"))
        assert default_quota_tracker.get_status(healthy_key)[0] == ProviderQuotaStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_chain_tries_hops_in_order(self) -> None:
        cfg = self._chain_config(
            SearchServiceConfig(search_service="tavily", api_key="tvly-key"),
            SearchServiceConfig(search_service="perplexity", api_key="pplx-key"),
            SearchServiceConfig(search_service="exa_ai", api_key="exa-key"),
        )
        searcher = WebSearcher(cfg)

        primary_service = AsyncMock()
        primary_service.search.side_effect = FakeAPIConnectionError(
            '{"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )

        fallback_service = AsyncMock()
        fallback_service.search.return_value = [
            SearchResult(title="Success", link="https://example.com", snippet="Test")
        ]

        call_count = {"perplexity": 0, "exa_ai": 0}

        async def mock_get_service(instance: WebSearcher, bypass_gateway: bool = False) -> SearchService:
            if instance.config.search_service == "tavily":
                return primary_service
            if instance.config.search_service == "perplexity":
                call_count["perplexity"] += 1
                return fallback_service
            if instance.config.search_service == "exa_ai":
                call_count["exa_ai"] += 1
                return AsyncMock()
            return AsyncMock()

        with patch.object(WebSearcher, "_get_search_service", mock_get_service):
            results = await searcher.search("test", 5)

        assert len(results) == 1
        assert call_count["perplexity"] == 1
        assert call_count["exa_ai"] == 0

    @pytest.mark.asyncio
    async def test_chain_hop_results_cached_on_hop(self) -> None:
        cfg = self._chain_config(
            SearchServiceConfig(search_service="tavily", api_key="tvly-key"),
            SearchServiceConfig(search_service="perplexity", api_key="pplx-key"),
        )
        searcher = WebSearcher(cfg)

        primary_service = AsyncMock()
        primary_service.search.side_effect = FakeAPIConnectionError(
            '{"detail":{"error":"This request exceeds your plan\'s set usage limit."}}'
        )

        fallback_service = AsyncMock()
        fallback_service.search.return_value = [
            SearchResult(title="Cached", link="https://cached.com", snippet="Cached result")
        ]

        async def mock_get_service(instance: WebSearcher, bypass_gateway: bool = False) -> SearchService:
            if instance.config.search_service == "tavily":
                return primary_service
            if instance.config.search_service == "perplexity":
                return fallback_service
            return AsyncMock()

        with patch.object(WebSearcher, "_get_search_service", mock_get_service):
            result1 = await searcher.search("cache-test-unique", 5)
            result2 = await searcher.search("cache-test-unique", 5)

        assert result1 == result2
        assert fallback_service.search.call_count == 1
