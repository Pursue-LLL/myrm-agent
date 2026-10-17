"""Priority provider chain integration tests (real services when available)."""

import os

import pytest
from myrm_agent_harness.toolkits.web_search.core.exceptions import (
    AllQueriesFailedError,
    SearchAPIError,
)
from myrm_agent_harness.toolkits.web_search.providers.chain import search_provider_chain
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    WebSearcher,
)


class TestProviderChainIntegration:
    """Provider chain integration (uses real services when available)."""

    @pytest.mark.asyncio
    async def test_chain_with_invalid_tavily_key(self):
        chain = [
            SearchServiceConfig(search_service="tavily", api_key="tvly-invalid-key-for-fallback-test"),
            SearchServiceConfig(search_service="searxng", api_base="http://localhost:8081"),
        ]

        try:
            results, winner = await search_provider_chain(chain, "Python programming", 3)

            assert len(results) > 0, "Chain should return results from SearXNG"
            assert winner == "searxng", "The invalid Tavily key must hand over to SearXNG"

            print(f"✓ Chain test passed: {len(results)} results from fallback hop")
        except (SearchAPIError, AllQueriesFailedError) as e:
            pytest.skip(f"SearXNG not available: {e}")

    @pytest.mark.asyncio
    async def test_no_chain_hop_when_primary_succeeds(self):
        api_key = os.getenv("TAVILY_API_KEY") or os.getenv("BASIC_API_KEY")
        if not api_key:
            pytest.skip("No valid Tavily API key available")

        chain = [
            SearchServiceConfig(search_service="tavily", api_key=api_key),
            SearchServiceConfig(search_service="searxng", api_base="http://localhost:8081"),
        ]

        try:
            results, winner = await search_provider_chain(chain, "AI news", 3)

            assert len(results) > 0
            assert winner == "tavily", "Chain hop should not occur when primary succeeds"

            print(f"✓ Primary service test passed: {len(results)} results from Tavily")
        except SearchAPIError as e:
            if "quota" in str(e).lower() or "429" in str(e):
                pytest.skip(f"Tavily quota exceeded: {e}")
            raise

    @pytest.mark.asyncio
    async def test_no_chain_when_not_configured(self):
        config = SearchServiceConfig(
            search_service="tavily",
            api_key="tvly-invalid-no-fallback",
        )

        searcher = WebSearcher(config)

        with pytest.raises(SearchAPIError):
            await searcher.search("test query", num_results=3)

    def test_config_loader_legacy_role_migration(self):
        from app.core.channel_bridge.config_parsers import (
            extract_active_search_config as _extract_active_search_config,
        )

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

        assert result is not None
        assert result.search_service == "tavily"
        assert result.api_key == "primary_key"
        assert result.provider_chain is not None
        assert len(result.provider_chain) == 2
        assert result.provider_chain[1].search_service == "searxng"
        assert result.provider_chain[1].api_base == "http://localhost:8081"

        print("✓ Config loader legacy role migration test passed")
