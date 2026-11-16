"""Merge behaviour of ``WebSearchTools.fast_search_with_questions``.

The results of every question go through one merge:
round-robin across questions -> URL/content dedup -> domain diversity -> first ``top_k``. With every result on its
own host the interleave keeps each question's share of the selection, which is what the tests below pin.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import NamedTuple
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_search.engine import WebSearchTools
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig


def _make_tools() -> WebSearchTools:
    config = SearchServiceConfig(search_service="searxng", api_key="key", api_base="http://localhost:8888")
    return WebSearchTools(config=config)


def _doc(owner: str, rank: int, text: str | None = None) -> Document:
    """Provider result owned by one question; every doc gets its own host so diversity decay stays neutral."""
    return Document(
        page_content=text or f"{owner} snippet number {rank}",
        metadata={"url": f"https://{owner}-r{rank}.example.com/page", "title": f"{owner} result {rank}"},
    )


def _page(host: str, rank: int) -> Document:
    """Provider result on a chosen host, for tests that exercise the same-domain decay."""
    return Document(
        page_content=f"{host} snippet number {rank}",
        metadata={"url": f"https://{host}/page-{rank}", "title": f"{host} result {rank}"},
    )


def _owner_counts(sources: list[dict[str, object]]) -> Counter[str]:
    """Count selected sources per owning question (host prefix before ``-r<rank>``)."""
    return Counter((urlparse(str(s["url"])).hostname or "").split("-r")[0] for s in sources)


def _provider_search(per_question: dict[str, list[Document]]) -> AsyncMock:
    """Stand-in for ``WebSearcher.multi_query_parallel_search`` returning each question's own documents."""

    async def search(
        queries: list[str],
        results_per_query: int,
        time_range: str | None = None,
    ) -> list[tuple[str, list[Document], Exception | None]]:
        return [(q, list(per_question.get(q, [])), None) for q in queries]

    return AsyncMock(side_effect=search)


class _ProviderCall(NamedTuple):
    queries: list[str]
    kwargs: Mapping[str, object]


def _provider_call(provider_search: AsyncMock) -> _ProviderCall:
    """The queries and keyword arguments of the one provider search the engine awaited."""
    provider_search.assert_awaited_once()
    call = provider_search.await_args
    assert call is not None
    return _ProviderCall(call.args[0], call.kwargs)


@pytest.mark.asyncio
class TestProviderPathMerge:
    """Merging what the configured search provider returned for each question."""

    async def test_unrelated_question_is_not_crowded_out(self) -> None:
        """A question whose results share no vocabulary with the others still keeps its share."""
        per_question = {
            "python decorators": [
                _doc("qa", r, f"python decorators guide part {r} decorators python") for r in range(6)
            ],
            "python generators": [
                _doc("qb", r, f"python generators guide part {r} generators python") for r in range(6)
            ],
            "recette tarte tatin": [
                _doc("qc", r, f"une preparation culinaire traditionnelle numero {r}") for r in range(6)
            ],
        }
        tools = _make_tools()

        with patch.object(tools._searcher, "multi_query_parallel_search", _provider_search(per_question)):
            sources, _ = await tools.fast_search_with_questions(questions=list(per_question), top_k=6)

        assert _owner_counts(sources) == {"qa": 2, "qb": 2, "qc": 2}

    @pytest.mark.parametrize("top_k", [3, 5, 7, 10])
    async def test_every_question_is_represented_for_any_top_k(self, top_k: int) -> None:
        per_question = {f"question {name}": [_doc(name, r) for r in range(10)] for name in ("qa", "qb", "qc")}
        tools = _make_tools()

        with patch.object(tools._searcher, "multi_query_parallel_search", _provider_search(per_question)):
            sources, _ = await tools.fast_search_with_questions(questions=list(per_question), top_k=top_k)

        counts = _owner_counts(sources)
        assert len(sources) == top_k
        assert set(counts) == {"qa", "qb", "qc"}
        assert max(counts.values()) - min(counts.values()) <= 1

    async def test_single_question_on_distinct_domains_keeps_search_engine_order(self) -> None:
        per_question = {"history of rome": [_doc("qa", r) for r in range(5)]}
        tools = _make_tools()

        with patch.object(tools._searcher, "multi_query_parallel_search", _provider_search(per_question)):
            sources, _ = await tools.fast_search_with_questions(questions=["history of rome"], top_k=3)

        assert [urlparse(str(s["url"])).hostname for s in sources] == [f"qa-r{r}.example.com" for r in range(3)]

    async def test_single_question_repeated_domain_is_moved_down_by_the_decay(self) -> None:
        """The engine's ranking stands except for the same-domain decay: a repeat host drops below a fresh one."""
        results = [_page("docs.example.com", 0), _page("docs.example.com", 1), _page("docs.example.com", 2)]
        results += [_page("other.example.org", 3), _page("docs.example.com", 4)]
        tools = _make_tools()

        with patch.object(
            tools._searcher, "multi_query_parallel_search", _provider_search({"history of rome": results})
        ):
            sources, _ = await tools.fast_search_with_questions(questions=["history of rome"], top_k=5)

        # decay score = 1 / (rank + 1) * 0.8 ** (earlier hits on the host): 1.0, 0.4, 0.213, 0.25, 0.102
        assert [urlparse(str(s["url"])).path for s in sources] == [
            "/page-0",
            "/page-1",
            "/page-3",
            "/page-2",
            "/page-4",
        ]

    async def test_duplicate_url_across_questions_is_selected_once(self) -> None:
        shared = _doc("shared", 0)
        per_question = {
            "capital of france": [shared, _doc("qa", 1), _doc("qa", 2)],
            "capital of spain": [shared, _doc("qb", 1), _doc("qb", 2)],
        }
        tools = _make_tools()

        with patch.object(tools._searcher, "multi_query_parallel_search", _provider_search(per_question)):
            sources, _ = await tools.fast_search_with_questions(questions=list(per_question), top_k=4)

        assert _owner_counts(sources) == {"shared": 1, "qa": 2, "qb": 1}

    async def test_top_k_zero_selects_nothing(self) -> None:
        per_question = {"history of rome": [_doc("qa", r) for r in range(3)]}
        tools = _make_tools()

        with patch.object(tools._searcher, "multi_query_parallel_search", _provider_search(per_question)):
            sources, formatted = await tools.fast_search_with_questions(questions=["history of rome"], top_k=0)

        assert sources == []
        assert formatted == ""

    @pytest.mark.parametrize("mirror_host", ["mirror.example.net", "www.mirror.example.net"])
    async def test_blocked_hostnames_drop_the_bare_host_and_the_www_alias(self, mirror_host: str) -> None:
        """A blocklist entry names a site, so its results are dropped on the bare host and on the www alias."""
        results = [_page(mirror_host, 0), _doc("qa", 1)]
        tools = _make_tools()

        with patch.object(
            tools._searcher, "multi_query_parallel_search", _provider_search({"history of rome": results})
        ):
            sources, _ = await tools.fast_search_with_questions(
                questions=["history of rome"], top_k=5, blocked_hostnames=("mirror.example.net",)
            )

        assert [urlparse(str(s["url"])).hostname for s in sources] == ["qa-r1.example.com"]

    async def test_source_links_are_the_links_the_provider_returned(self) -> None:
        """Dedup folds case and www for comparison only: the link a source shows is the provider's own."""
        link = "https://www.example.com/Docs/GuideAb12"
        document = Document(page_content="tutorial", metadata={"url": link, "title": "Guide"})
        tools = _make_tools()

        with patch.object(
            tools._searcher, "multi_query_parallel_search", _provider_search({"history of rome": [document]})
        ):
            sources, _ = await tools.fast_search_with_questions(questions=["history of rome"], top_k=3)

        assert [s["url"] for s in sources] == [link]


@pytest.mark.asyncio
class TestProviderPathQueries:
    """What the provider receives for the questions the agent asked."""

    @pytest.mark.parametrize(
        "question",
        [
            "latest AI news today",
            "TSLA stock price today",
            "tikv raft rust implementation source code",
            "famous movie quotes about time",
            "site:gov.cn digital economy policy",
        ],
    )
    async def test_queries_reach_the_provider_as_written(self, question: str) -> None:
        """Topic words never steer the search: no engine, category or time parameter is inferred from them."""
        tools = _make_tools()
        provider_search = _provider_search({question: [_doc("qa", 0)]})

        with patch.object(tools._searcher, "multi_query_parallel_search", provider_search):
            await tools.fast_search_with_questions(questions=[question], top_k=3)

        call = _provider_call(provider_search)
        assert call.queries == [question]
        assert call.kwargs == {"time_range": None}

    async def test_cve_and_doi_are_pinned_as_exact_phrases(self) -> None:
        question = "Explain CVE-2024-38077 and 10.1038/s41586-024-07487-w"
        pinned = 'Explain "CVE-2024-38077" and "10.1038/s41586-024-07487-w"'
        tools = _make_tools()
        provider_search = _provider_search({pinned: [_doc("qa", 0)]})

        with patch.object(tools._searcher, "multi_query_parallel_search", provider_search):
            await tools.fast_search_with_questions(questions=[question], top_k=3)

        assert _provider_call(provider_search).queries == [pinned]

    async def test_time_range_travels_with_the_provider_search(self) -> None:
        question = "openai announcements"
        tools = _make_tools()
        provider_search = _provider_search({question: [_doc("qa", 0)]})

        with patch.object(tools._searcher, "multi_query_parallel_search", provider_search):
            await tools.fast_search_with_questions(questions=[question], top_k=3, time_range="week")

        assert _provider_call(provider_search).kwargs == {"time_range": "week"}
