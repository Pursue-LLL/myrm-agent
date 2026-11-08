"""Merge behaviour of ``WebSearchTools.fast_search_with_questions``.

Every query source (configured provider, Bilibili API) goes through one merge:
round-robin across questions -> URL/content dedup -> domain diversity -> first ``top_k``. With every result on its
own host the interleave keeps each question's share of the selection, which is what the tests below pin.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping
from typing import NamedTuple
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.exceptions import AllQueriesFailedError
from myrm_agent_harness.toolkits.web_search.engine import WebSearchTools
from myrm_agent_harness.toolkits.web_search.providers.bilibili_search import is_bilibili_video_query
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig

_SEARCH_BILIBILI = "myrm_agent_harness.toolkits.web_search.providers.bilibili_search.search_bilibili"

# Every question is scoped to Bilibili videos by site:, so the Bilibili API answers them.
_BILIBILI_QUESTIONS = (
    "site:bilibili.com python decorators",
    "site:bilibili.com rust ownership",
    "site:bilibili.com kubernetes operators",
)


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


def _bilibili_api(per_query: dict[str, list[SearchResult]]) -> AsyncMock:
    """Stand-in for ``search_bilibili`` answering per query; a query it does not know gets ``None`` (API failure)."""

    async def search(query: str, max_results: int) -> list[SearchResult] | None:
        return per_query.get(query)

    return AsyncMock(side_effect=search)


def _bilibili_video(question_idx: int, rank: int) -> SearchResult:
    return SearchResult(
        title=f"video {question_idx}-{rank}",
        link=f"https://www.bilibili.com/video/BV{question_idx}Ab{rank}",
        snippet=f"uploader {question_idx} episode {rank}",
    )


def test_bilibili_questions_are_recognised() -> None:
    assert all(is_bilibili_video_query(q) for q in _BILIBILI_QUESTIONS)


@pytest.mark.asyncio
class TestProviderPathMerge:
    """Questions served by the configured search provider."""

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


@pytest.mark.asyncio
class TestNativeBilibiliPathMerge:
    """All questions routed to Bilibili are answered by the Bilibili API."""

    async def test_every_question_keeps_its_share(self) -> None:
        per_query = {q: [_bilibili_video(idx, rank) for rank in range(4)] for idx, q in enumerate(_BILIBILI_QUESTIONS)}
        tools = _make_tools()

        with patch(_SEARCH_BILIBILI, _bilibili_api(per_query)):
            sources, _ = await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3)

        assert sorted(str(s["url"]).rsplit("/", 1)[1][:3] for s in sources) == ["BV0", "BV1", "BV2"]

    async def test_source_links_are_the_links_the_api_returned(self) -> None:
        """Dedup folds case and www for comparison only: the link a source shows is the API's own."""
        link = "https://www.bilibili.com/video/BV1hp4y1k7SV"
        per_query = {_BILIBILI_QUESTIONS[0]: [SearchResult(title="Rust", link=link, snippet="tutorial")]}
        tools = _make_tools()

        with patch(_SEARCH_BILIBILI, _bilibili_api(per_query)):
            sources, _ = await tools.fast_search_with_questions(questions=[_BILIBILI_QUESTIONS[0]], top_k=3)

        assert [s["url"] for s in sources] == [link]

    async def test_questions_are_searched_concurrently(self) -> None:
        """Every question is in flight before any answer returns: the wait is one request, not one per question."""
        started: set[str] = set()
        all_started = asyncio.Event()

        async def search(query: str, max_results: int) -> list[SearchResult] | None:
            started.add(query)
            if len(started) == len(_BILIBILI_QUESTIONS):
                all_started.set()
            await all_started.wait()
            return [_bilibili_video(_BILIBILI_QUESTIONS.index(query), 0)]

        tools = _make_tools()

        with patch(_SEARCH_BILIBILI, AsyncMock(side_effect=search)):
            sources, _ = await asyncio.wait_for(
                tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3), timeout=5
            )

        assert len(sources) == 3

    @pytest.mark.parametrize("mirror_host", ["mirror.example.net", "www.mirror.example.net"])
    async def test_blocked_hostnames_apply_to_native_results(self, mirror_host: str) -> None:
        """A blocklist entry names a site, so its results are dropped on the bare host and on the www alias."""
        per_query = {
            _BILIBILI_QUESTIONS[0]: [
                SearchResult(title="blocked mirror", link=f"https://{mirror_host}/video/1", snippet="mirrored"),
                _bilibili_video(0, 0),
            ]
        }
        tools = _make_tools()

        with patch(_SEARCH_BILIBILI, _bilibili_api(per_query)):
            sources, _ = await tools.fast_search_with_questions(
                questions=[_BILIBILI_QUESTIONS[0]], top_k=5, blocked_hostnames=("mirror.example.net",)
            )

        assert [urlparse(str(s["url"])).hostname for s in sources] == ["www.bilibili.com"]

    async def test_falls_back_to_the_provider_with_the_questions_as_written(self) -> None:
        per_question = {q: [_doc(f"q{idx}", 0)] for idx, q in enumerate(_BILIBILI_QUESTIONS)}
        tools = _make_tools()
        provider_search = _provider_search(per_question)

        with (
            patch(_SEARCH_BILIBILI, _bilibili_api({})),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            sources, _ = await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3)

        assert _provider_call(provider_search).queries == list(_BILIBILI_QUESTIONS)
        assert len(sources) == 3

    async def test_only_the_questions_the_api_could_not_answer_go_to_the_provider(self) -> None:
        unanswered = _BILIBILI_QUESTIONS[1]
        answered = {q: [_bilibili_video(idx, 0)] for idx, q in enumerate(_BILIBILI_QUESTIONS) if q != unanswered}
        tools = _make_tools()
        provider_search = _provider_search({unanswered: [_doc("q1", 0)]})

        with (
            patch(_SEARCH_BILIBILI, _bilibili_api(answered)),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            sources, _ = await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3)

        assert _provider_call(provider_search).queries == [unanswered]
        assert len(sources) == 3

    async def test_a_failed_provider_search_keeps_what_the_api_answered(self) -> None:
        answered, unanswered = _BILIBILI_QUESTIONS[0], _BILIBILI_QUESTIONS[1]
        tools = _make_tools()
        provider_search = AsyncMock(side_effect=AllQueriesFailedError("Web search failed: unreachable"))

        with (
            patch(_SEARCH_BILIBILI, _bilibili_api({answered: [_bilibili_video(0, 0)]})),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            sources, _ = await tools.fast_search_with_questions(questions=[answered, unanswered], top_k=3)

        provider_search.assert_awaited_once()
        assert [s["url"] for s in sources] == ["https://www.bilibili.com/video/BV0Ab0"]

    async def test_the_provider_error_surfaces_when_the_api_answered_nothing(self) -> None:
        tools = _make_tools()
        provider_search = AsyncMock(side_effect=AllQueriesFailedError("Web search failed: unreachable"))

        with (
            patch(_SEARCH_BILIBILI, _bilibili_api({})),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
            pytest.raises(AllQueriesFailedError),
        ):
            await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3)

    async def test_explicit_time_range_goes_to_the_provider_instead_of_the_api(self) -> None:
        """The API request carries no date parameter, so the provider search applies the time window."""
        per_query = {q: [_bilibili_video(idx, 0)] for idx, q in enumerate(_BILIBILI_QUESTIONS)}
        per_question = {q: [_doc(f"q{idx}", 0)] for idx, q in enumerate(_BILIBILI_QUESTIONS)}
        tools = _make_tools()
        bilibili_api = _bilibili_api(per_query)
        provider_search = _provider_search(per_question)

        with (
            patch(_SEARCH_BILIBILI, bilibili_api),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3, time_range="week")

        bilibili_api.assert_not_awaited()
        call = _provider_call(provider_search)
        assert call.queries == list(_BILIBILI_QUESTIONS)
        assert call.kwargs == {"time_range": "week"}

    async def test_a_mixed_question_set_goes_to_the_provider_unchanged(self) -> None:
        """The API answers only when every question is scoped to Bilibili videos."""
        questions = [_BILIBILI_QUESTIONS[0], "history of rome"]
        tools = _make_tools()
        bilibili_api = _bilibili_api({})
        provider_search = _provider_search({q: [_doc(f"q{idx}", 0)] for idx, q in enumerate(questions)})

        with (
            patch(_SEARCH_BILIBILI, bilibili_api),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            await tools.fast_search_with_questions(questions=questions, top_k=3)

        bilibili_api.assert_not_awaited()
        assert _provider_call(provider_search).queries == questions
