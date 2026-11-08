"""What the web_search tool tells the model about a time_range the serving providers could not honor.

The ``Time filter notice`` is the tool's own statement, appended after the untrusted search block. It names only the
providers that returned the displayed results, so a standby provider that never served is not blamed.

[POS]
web_search tool level tests; the engine is replaced by a double, so no provider is called. How the constraints reach
the serving provider is covered in test_search_constraints.py and the mapping tables in test_explicit_params.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import AsyncMock, patch

import pytest
from langchain.tools import BaseTool

from myrm_agent_harness.core.config.llm import LLMConfig
from myrm_agent_harness.toolkits.retriever.sufficiency import SufficiencyConfig, SufficiencyVerdict
from myrm_agent_harness.toolkits.web_search import engine as engine_mod
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig
from myrm_agent_harness.toolkits.web_search.web_search_agent_tools import create_web_search_tool


def _tool(provider: str, chain: tuple[str, ...] = ()) -> BaseTool:
    hops = [SearchServiceConfig(search_service=slug, api_key="key") for slug in chain] or None
    return create_web_search_tool(SearchServiceConfig(search_service=provider, api_key="key", provider_chain=hops))


def _served_by(*providers: str) -> list[dict[str, object]]:
    """Source entries as the engine returns them: one result per named provider."""
    return [{"url": f"https://example.com/{index}", "search_provider": slug} for index, slug in enumerate(providers)]


async def _run_tool(
    tool: BaseTool, sources: list[dict[str, object]] | None = None, **arguments: object
) -> tuple[dict[str, object], AsyncMock]:
    with patch.object(engine_mod.WebSearchTools, "fast_search_with_questions", new_callable=AsyncMock) as engine:
        engine.return_value = (sources or [], "【1】 result snippet")
        result = await tool.ainvoke({"questions": ["recent changes"], "reason": "", **arguments})
    return result, engine


def _engine_kwargs(engine: AsyncMock) -> Mapping[str, object]:
    assert engine.await_args is not None
    return engine.await_args.kwargs


class TestToolDisclosure:
    @pytest.mark.asyncio
    async def test_time_range_reaches_the_engine_and_defaults_to_none(self) -> None:
        _, engine = await _run_tool(_tool("tavily"), time_range="week")
        assert _engine_kwargs(engine)["time_range"] == "week"

        _, engine = await _run_tool(_tool("tavily"))
        assert _engine_kwargs(engine)["time_range"] is None

    @pytest.mark.asyncio
    async def test_a_shortfall_is_stated_after_the_untrusted_block(self) -> None:
        result, _ = await _run_tool(_tool("perplexity"), _served_by("perplexity"), time_range="week")

        content = str(result["content"])
        assert content.endswith(
            "Time filter notice: time filters are not passed to perplexity, so time_range 'week' was not applied."
        )
        assert content.index("Time filter notice") > content.index("<<<END_UNTRUSTED_DATA")

    @pytest.mark.asyncio
    async def test_a_standby_provider_that_cannot_apply_the_range_is_not_blamed(self) -> None:
        tool = _tool("tavily", chain=("tavily", "perplexity"))

        result, _ = await _run_tool(tool, _served_by("tavily"), time_range="week")

        assert "Time filter notice" not in str(result["content"])

    @pytest.mark.asyncio
    async def test_a_failover_provider_that_served_is_named(self) -> None:
        tool = _tool("tavily", chain=("tavily", "perplexity"))

        result, _ = await _run_tool(tool, _served_by("perplexity"), time_range="week")

        content = str(result["content"])
        assert "not passed to perplexity" in content
        assert "tavily" not in content

    @pytest.mark.asyncio
    async def test_every_serving_provider_with_a_shortfall_is_named(self) -> None:
        tool = _tool("tavily", chain=("tavily", "perplexity", "brave"))

        result, _ = await _run_tool(tool, _served_by("tavily", "perplexity", "brave"), time_range="week")

        content = str(result["content"])
        assert "not passed to perplexity" in content
        assert "not passed to brave" in content
        assert "tavily" not in content

    @pytest.mark.asyncio
    async def test_results_naming_no_provider_fall_back_to_every_configured_one(self) -> None:
        result, _ = await _run_tool(_tool("tavily", chain=("tavily", "perplexity")), time_range="week")

        content = str(result["content"])
        assert "not passed to perplexity" in content
        assert "tavily" not in content

    @pytest.mark.asyncio
    async def test_nothing_is_added_when_the_provider_applies_the_range(self) -> None:
        result, _ = await _run_tool(_tool("tavily"), _served_by("tavily"), time_range="week")

        assert "Time filter notice" not in str(result["content"])

    @pytest.mark.asyncio
    async def test_nothing_is_added_without_a_time_range(self) -> None:
        result, _ = await _run_tool(_tool("perplexity"))

        assert "Time filter notice" not in str(result["content"])

    @pytest.mark.asyncio
    async def test_metadata_carries_only_what_consumers_read(self) -> None:
        result, _ = await _run_tool(_tool("tavily"))

        assert result["metadata"] == {"sources": []}

    @pytest.mark.asyncio
    async def test_the_returned_sources_drop_the_provider_tag_the_notice_was_built_from(self) -> None:
        result, _ = await _run_tool(_tool("perplexity"), _served_by("perplexity"), time_range="week")

        assert result["metadata"] == {"sources": [{"url": "https://example.com/0"}]}
        assert "not passed to perplexity" in str(result["content"])

    @pytest.mark.asyncio
    async def test_a_sufficiency_verdict_is_stated_in_the_content_only(self) -> None:
        verdict = SufficiencyVerdict(
            is_sufficient=False,
            confidence=0.9,
            missing_aspects=("release date",),
            suggested_queries=("release date 2026",),
        )
        tool = create_web_search_tool(
            SearchServiceConfig(search_service="tavily", api_key="key"),
            SufficiencyConfig(enabled=True),
            LLMConfig(model="mock-provider/mock-model", api_key="mock-key"),
        )

        with patch(
            "myrm_agent_harness.toolkits.retriever.sufficiency.evaluate_sufficiency",
            AsyncMock(return_value=verdict),
        ):
            result, _ = await _run_tool(tool)

        assert "Retrieval Sufficiency Notice" in str(result["content"])
        assert "release date 2026" in str(result["content"])
        assert result["metadata"] == {"sources": []}
