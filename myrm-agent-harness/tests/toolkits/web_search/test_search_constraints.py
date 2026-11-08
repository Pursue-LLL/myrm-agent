"""Explicit search constraints reaching the provider that serves each request.

The agent's ``site:`` operators and time_range are mapped by the provider hop that serves the request (never once for
the whole chain) and are part of the result-cache key. Results name the provider that served them, and a search that
came back empty names the time_range as a possible cause only when a provider the config can reach maps it.

[POS]
WebSearcher / provider-chain level tests. The mapping tables themselves are covered in test_explicit_params.py and
what the tool tells the model in test_search_constraint_disclosure.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_search import engine as engine_mod
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.exceptions import AllQueriesFailedError
from myrm_agent_harness.toolkits.web_search.providers.chain import ProviderQuotaTracker, search_provider_chain
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig, WebSearcher


def _result(name: str) -> SearchResult:
    return SearchResult(title=name, link=f"https://example.com/{name}", snippet=f"{name} snippet")


class _RecordingService:
    """Search client double that records the query and the provider parameters of every call."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.queries: list[str] = []
        self.calls: list[dict[str, object]] = []
        self._results = results

    async def search(self, query: str, num_results: int = 5, **kwargs: object) -> list[SearchResult]:
        self.queries.append(query)
        self.calls.append(kwargs)
        if self._results is not None:
            return self._results
        return [SearchResult(title="t", link=f"https://example.com/{query}", snippet="s")]


def _searcher(
    provider: str,
    extra_params: dict[str, object] | None = None,
    results: list[SearchResult] | None = None,
) -> tuple[WebSearcher, _RecordingService]:
    searcher = WebSearcher(SearchServiceConfig(search_service=provider, api_key="key", extra_params=extra_params))
    service = _RecordingService(results)
    searcher._search_service = service
    return searcher, service


def _serve_hops_from(
    monkeypatch: pytest.MonkeyPatch, services: Mapping[str, _RecordingService]
) -> list[SearchServiceConfig]:
    """Route each chain hop to its own service and return the hop configs in priority order."""

    async def fake_get_service(self: WebSearcher, bypass_gateway: bool = False) -> _RecordingService:
        return services[self.config.search_service]

    monkeypatch.setattr(WebSearcher, "_get_search_service", fake_get_service)
    return [SearchServiceConfig(search_service=slug, api_key="key") for slug in services]


class TestSiteOperatorsReachTheServingProvider:
    @pytest.mark.asyncio
    async def test_tavily_receives_the_operators_as_domain_filters(self) -> None:
        searcher, service = _searcher("tavily")

        await searcher.search("site:gov.cn -site:reddit.com digital policy")

        assert service.queries == ["digital policy"]
        assert service.calls == [{"search_domain_filter": ["gov.cn"], "exclude_domains": ["reddit.com"]}]

    @pytest.mark.asyncio
    async def test_a_provider_with_no_domain_filter_mapping_receives_the_query_as_written(self) -> None:
        searcher, service = _searcher("searxng")

        await searcher.search("site:gov.cn digital policy")

        assert service.queries == ["site:gov.cn digital policy"]
        assert "search_domain_filter" not in service.calls[0]

    @pytest.mark.asyncio
    async def test_operators_win_over_the_configured_domain_filter(self) -> None:
        searcher, service = _searcher("tavily", {"search_domain_filter": ["old.example"], "topic": "news"})

        await searcher.search("site:gov.cn policy")

        assert service.calls == [{"search_domain_filter": ["gov.cn"], "topic": "news"}]

    @pytest.mark.asyncio
    async def test_different_operators_never_share_a_cached_answer(self) -> None:
        searcher, service = _searcher("tavily")

        await searcher.search("site:gov.cn policy")
        await searcher.search("site:edu.cn policy")

        assert [call["search_domain_filter"] for call in service.calls] == [["gov.cn"], ["edu.cn"]]

    @pytest.mark.asyncio
    async def test_a_failover_hop_receives_the_operators_in_its_own_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        services = {"tavily": _RecordingService(results=[]), "searxng": _RecordingService()}
        hops = _serve_hops_from(monkeypatch, services)

        _, winner = await search_provider_chain(
            hops, "site:gov.cn digital policy", 5, quota_tracker=ProviderQuotaTracker()
        )

        assert winner == "searxng"
        assert services["tavily"].queries == ["digital policy"]
        assert services["tavily"].calls == [{"search_domain_filter": ["gov.cn"]}]
        assert services["searxng"].queries == ["site:gov.cn digital policy"]
        assert "search_domain_filter" not in services["searxng"].calls[0]

    @pytest.mark.asyncio
    async def test_the_bilibili_fallback_keeps_the_scope_as_written_on_tavily(self) -> None:
        searcher, service = _searcher("tavily")

        # An explicit time_range skips the Bilibili API, so the provider search carries the whole constraint.
        await engine_mod.WebSearchTools(searcher=searcher).fast_search_with_questions(
            ["site:bilibili.com/video LLM"], time_range="week"
        )

        assert service.queries == ["LLM"]
        assert service.calls == [{"search_domain_filter": ["bilibili.com/video"], "time_range": "week"}]

    @pytest.mark.asyncio
    async def test_the_bilibili_fallback_pins_identifiers_like_every_other_route(self) -> None:
        searcher, service = _searcher("tavily")

        await engine_mod.WebSearchTools(searcher=searcher).fast_search_with_questions(
            ["site:bilibili.com 关于 CVE-2024-3094 的视频"], time_range="week"
        )

        assert service.queries == ['关于 "CVE-2024-3094" 的视频']


class TestTimeRangeReachesTheServingProvider:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ("searxng", {"time_range": "week"}),
            ("tavily", {"time_range": "week"}),
            ("volcengine_doubao", {"TimeRange": "OneWeek"}),
        ],
    )
    async def test_a_bucket_is_sent_in_the_providers_own_parameter(
        self, provider: str, expected: dict[str, str]
    ) -> None:
        searcher, service = _searcher(provider)

        await searcher.search("recent changes", time_range="week")

        assert expected.items() <= service.calls[0].items()

    @pytest.mark.asyncio
    async def test_a_provider_without_time_parameters_receives_none(self) -> None:
        searcher, service = _searcher("brave")

        await searcher.search("recent changes", time_range="week")

        assert service.calls == [{}]

    @pytest.mark.asyncio
    async def test_an_unparseable_value_sends_nothing(self) -> None:
        searcher, service = _searcher("tavily")

        await searcher.search("recent changes", time_range="last tuesday")

        assert service.calls == [{}]

    @pytest.mark.asyncio
    async def test_time_range_wins_over_the_configured_time_parameter(self) -> None:
        searcher, service = _searcher("searxng", {"time_range": "year"})

        await searcher.search("recent changes", time_range="day")

        assert service.calls[0]["time_range"] == "day"

    @pytest.mark.asyncio
    async def test_different_time_ranges_never_share_a_cached_answer(self) -> None:
        searcher, service = _searcher("searxng")

        await searcher.search("recent changes", time_range="day")
        await searcher.search("recent changes", time_range="week")

        assert [call["time_range"] for call in service.calls] == ["day", "week"]

    @pytest.mark.asyncio
    async def test_each_chain_hop_maps_the_time_range_for_its_own_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        today = date.today()
        start, end = today - timedelta(days=20), today - timedelta(days=10)
        services = {"tavily": _RecordingService(results=[]), "searxng": _RecordingService()}
        hops = _serve_hops_from(monkeypatch, services)

        _, winner = await search_provider_chain(
            hops, "chain query", 5, time_range=f"{start}..{end}", quota_tracker=ProviderQuotaTracker()
        )

        assert winner == "searxng"
        assert services["tavily"].calls == [{"start_date": start.isoformat(), "end_date": end.isoformat()}]
        assert services["searxng"].calls[0]["time_range"] == "month"


class TestResultsNameTheirProvider:
    @pytest.mark.asyncio
    async def test_a_search_stamps_its_provider_on_every_result(self) -> None:
        searcher, _ = _searcher("tavily", results=[_result("a"), _result("b")])

        results = await searcher.search("provider stamp")

        assert [result.provider for result in results] == ["tavily", "tavily"]

    @pytest.mark.asyncio
    async def test_a_cached_answer_keeps_naming_its_provider(self) -> None:
        searcher, service = _searcher("tavily")

        await searcher.search("provider stamp")
        cached = await searcher.search("provider stamp")

        assert len(service.calls) == 1
        assert [result.provider for result in cached] == ["tavily"]

    @pytest.mark.asyncio
    async def test_a_failover_result_names_the_hop_that_answered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        services = {"tavily": _RecordingService(results=[]), "searxng": _RecordingService()}
        hops = _serve_hops_from(monkeypatch, services)

        results, winner = await search_provider_chain(hops, "failover stamp", 5, quota_tracker=ProviderQuotaTracker())

        assert winner == "searxng"
        assert [result.provider for result in results] == ["searxng"]

    @pytest.mark.asyncio
    async def test_sources_name_their_provider_and_the_model_text_does_not(self) -> None:
        searcher, _ = _searcher("tavily")

        sources, context = await engine_mod.WebSearchTools(searcher=searcher).fast_search_with_questions(
            ["provider sources"]
        )

        assert [source["search_provider"] for source in sources] == ["tavily"]
        assert "tavily" not in context

    def test_documents_sharing_a_url_form_one_source_naming_the_first_provider(self) -> None:
        documents = [
            Document(page_content="a", metadata={"url": "https://example.com/1", "search_provider": "tavily"}),
            Document(page_content="b", metadata={"url": "https://example.com/1", "search_provider": "searxng"}),
        ]
        sources: list[dict[str, object]] = [{"url": "https://example.com/1"}]

        engine_mod._attach_search_providers(sources, documents)

        assert sources == [{"url": "https://example.com/1", "search_provider": "tavily"}]

    def test_a_source_whose_documents_name_no_provider_stays_unnamed(self) -> None:
        documents = [Document(page_content="a", metadata={"url": "https://example.com/1"})]
        sources: list[dict[str, object]] = [{"url": "https://example.com/1"}]

        engine_mod._attach_search_providers(sources, documents)

        assert sources == [{"url": "https://example.com/1"}]


class TestZeroResultMessage:
    @pytest.mark.asyncio
    async def test_names_the_time_range_a_provider_received(self) -> None:
        searcher, _ = _searcher("searxng", results=[])

        with pytest.raises(AllQueriesFailedError) as exc_info:
            await searcher.multi_query_parallel_search(["quiet topic"], 5, time_range="week")

        assert "time_range 'week'" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_does_not_mention_a_time_range_that_was_not_set(self) -> None:
        searcher, _ = _searcher("searxng", results=[])

        with pytest.raises(AllQueriesFailedError) as exc_info:
            await searcher.multi_query_parallel_search(["quiet topic"], 5)

        assert "time_range" not in exc_info.value.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("provider", "time_range"),
        [
            ("brave", "week"),  # no time parameters are mapped for this provider
            ("searxng", "last fortnight"),  # neither day/week/month/year nor a date range
            ("searxng", "2020-01-01..2020-01-31"),  # SearXNG drops a range that starts over a year ago
        ],
    )
    async def test_does_not_blame_a_time_range_the_provider_never_received(
        self, provider: str, time_range: str
    ) -> None:
        searcher, _ = _searcher(provider, results=[])

        with pytest.raises(AllQueriesFailedError) as exc_info:
            await searcher.multi_query_parallel_search(["quiet topic"], 5, time_range=time_range)

        assert "time_range" not in exc_info.value.message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("slugs", "names_the_time_range"),
        [
            (["brave", "tavily"], True),
            (["tavily", "brave"], True),
            (["brave", "exa_ai"], False),
        ],
    )
    async def test_a_chain_names_the_time_range_when_any_hop_received_it(
        self, monkeypatch: pytest.MonkeyPatch, slugs: list[str], names_the_time_range: bool
    ) -> None:
        hops = _serve_hops_from(monkeypatch, {slug: _RecordingService(results=[]) for slug in slugs})
        searcher = WebSearcher(SearchServiceConfig(search_service=slugs[0], api_key="key", provider_chain=hops))

        with pytest.raises(AllQueriesFailedError) as exc_info:
            await searcher.multi_query_parallel_search(["quiet topic"], 5, time_range="week")

        assert ("time_range 'week'" in exc_info.value.message) is names_the_time_range
