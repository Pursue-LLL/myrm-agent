"""Fallback Provider集成测试（真实场景）"""

import os

import pytest
from myrm_agent_harness.toolkits.web_search.exceptions import SearchAPIError
from myrm_agent_harness.toolkits.web_search.metrics import WebSearchMetrics
from myrm_agent_harness.toolkits.web_search.web_searcher import SearchServiceConfig, WebSearcher


class TestFallbackIntegration:
    """Fallback集成测试（使用真实服务）"""

    @pytest.mark.asyncio
    async def test_fallback_with_invalid_tavily_key(self):
        """测试Tavily配额超限后fallback到SearXNG"""
        fallback_config = SearchServiceConfig(
            search_service="searxng",
            api_base="http://localhost:8081",
        )

        primary_config = SearchServiceConfig(
            search_service="tavily",
            api_key="tvly-invalid-key-for-fallback-test",
            fallback_config=fallback_config,
        )

        metrics = WebSearchMetrics()
        searcher = WebSearcher(primary_config, metrics=metrics)

        try:
            results = await searcher.search("Python programming", num_results=3)

            assert len(results) > 0, "Fallback should return results"

            snap = metrics.snapshot()
            assert snap["fallback_triggered_count"] >= 1, "Fallback should be triggered"
            assert snap["fallback_successes"] >= 1, "Fallback should succeed"

            print(f"✓ Fallback test passed: {len(results)} results from SearXNG")
        except SearchAPIError as e:
            pytest.skip(f"SearXNG not available: {e}")

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_succeeds(self):
        """测试主服务成功时不触发fallback"""
        api_key = os.getenv("TAVILY_API_KEY") or os.getenv("BASIC_API_KEY")
        if not api_key:
            pytest.skip("No valid Tavily API key available")

        fallback_config = SearchServiceConfig(search_service="searxng")
        primary_config = SearchServiceConfig(
            search_service="tavily",
            api_key=api_key,
            fallback_config=fallback_config,
        )

        metrics = WebSearchMetrics()
        searcher = WebSearcher(primary_config, metrics=metrics)

        try:
            results = await searcher.search("AI news", num_results=3)

            assert len(results) > 0

            snap = metrics.snapshot()
            assert snap["fallback_triggered_count"] == 0, "Fallback should not be triggered"

            print(f"✓ Primary service test passed: {len(results)} results from Tavily")
        except SearchAPIError as e:
            if "quota" in str(e).lower() or "429" in str(e):
                pytest.skip(f"Tavily quota exceeded: {e}")
            raise

    @pytest.mark.asyncio
    async def test_no_fallback_when_not_configured(self):
        """测试未配置fallback时的行为"""
        config = SearchServiceConfig(
            search_service="tavily",
            api_key="tvly-invalid-no-fallback",
        )

        metrics = WebSearchMetrics()
        searcher = WebSearcher(config, metrics=metrics)

        with pytest.raises(SearchAPIError):
            await searcher.search("test query", num_results=3)

        snap = metrics.snapshot()
        assert snap["fallback_triggered_count"] == 0
        assert snap["search_terminal_failures"] >= 1

    def test_config_loader_role_extraction(self):
        """测试config_loader正确提取primary和fallback角色"""
        from app.core.channel_bridge.config_parsers import extract_active_search_config as _extract_active_search_config

        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "role": "primary",
                    "search_service": "tavily",
                    "api_key": "primary_key",
                },
                {
                    "id": "2",
                    "enabled": True,
                    "role": "fallback",
                    "search_service": "searxng",
                    "api_base": "http://localhost:8081",
                },
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "tavily"
        assert result.api_key == "primary_key"
        assert result.fallback_config is not None
        assert result.fallback_config.search_service == "searxng"
        assert result.fallback_config.api_base == "http://localhost:8081"

        print("✓ Config loader role extraction test passed")
