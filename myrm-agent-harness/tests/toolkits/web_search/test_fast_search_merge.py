"""Merge behaviour of ``WebSearchTools.fast_search_with_questions``.

Every query source (configured provider, Bilibili API, GitHub code search) goes through one merge:
round-robin across questions -> URL/content dedup -> domain diversity -> first ``top_k``. These tests
pin the property that makes multi-question calls reliable: no question is crowded out of the selection.
"""

from __future__ import annotations

from collections import Counter
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.engine import WebSearchTools
from myrm_agent_harness.toolkits.web_search.processing.intent_optimizer import (
    SearchIntent,
    detect_search_intent,
    resolve_search_params,
)
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig

_SEARCH_BILIBILI = "myrm_agent_harness.toolkits.web_search.providers.bilibili_search.search_bilibili"
_SEARCH_GITHUB_CODE = "myrm_agent_harness.toolkits.web_search.providers.github_code_search.search_github_code"

# Detected as CODE intent: answered by GitHub code search when every question is CODE.
_CODE_QUESTIONS = (
    "tikv raft rust implementation source code",
    "etcd raft go implementation source code",
    "hashicorp raft go implementation source code",
)

# Detected as PLATFORM_BILIBILI intent: answered by the Bilibili API when every question is.
_BILIBILI_QUESTIONS = (
    "site:bilibili.com python decorators",
    "site:bilibili.com rust ownership",
    "site:bilibili.com kubernetes operators",
)


def _make_tools() -> WebSearchTools:
    config = SearchServiceConfig(search_service="searxng", search_service_url="http://localhost:8888")
    return WebSearchTools(config=config)


def _doc(owner: str, rank: int, text: str | None = None) -> Document:
    """Provider result owned by one question; every doc gets its own host so diversity decay stays neutral."""
    return Document(
        page_content=text or f"{owner} snippet number {rank}",
        metadata={"url": f"https://{owner}-r{rank}.example.com/page", "title": f"{owner} result {rank}"},
    )


def _owner_counts(sources: list[dict[str, object]]) -> Counter[str]:
    """Count selected sources per owning question (host prefix before ``-r<rank>``)."""
    return Counter((urlparse(str(s["url"])).hostname or "").split("-r")[0] for s in sources)


def _provider_search(per_question: dict[str, list[Document]]) -> AsyncMock:
    """Stand-in for ``WebSearcher.multi_query_parallel_search`` returning each question's own documents."""

    async def search(
        queries: list[str], results_per_query: int, per_query_overrides: object = None
    ) -> list[tuple[str, list[Document], Exception | None]]:
        return [(q, list(per_question.get(q, [])), None) for q in queries]

    return AsyncMock(side_effect=search)


def _native_search(per_query: dict[str, list[SearchResult]]) -> AsyncMock:
    """Stand-in for a native source (Bilibili API / GitHub code search) answering per query."""

    async def search(query: str, max_results: int) -> list[SearchResult] | None:
        return per_query.get(query)

    return AsyncMock(side_effect=search)


def _github_result(repo: str, symbol: str) -> SearchResult:
    return SearchResult(
        title=f"{repo}: src/lib.rs",
        link=f"https://github.com/{repo}/blob/master/src/lib.rs",
        snippet=f"Repository: {repo}\nCode Fragment:\nfn {symbol}()",
        engines=["github_code"],
    )


def _bilibili_video(question_idx: int, rank: int) -> SearchResult:
    return SearchResult(
        title=f"video {question_idx}-{rank}",
        link=f"https://www.bilibili.com/video/bv{question_idx}x{rank}",
        snippet=f"uploader {question_idx} episode {rank}",
    )


def test_code_questions_are_detected_as_code_intent() -> None:
    assert {detect_search_intent(q).intent for q in _CODE_QUESTIONS} == {SearchIntent.CODE}


def test_bilibili_questions_are_detected_as_bilibili_intent() -> None:
    assert {detect_search_intent(q).intent for q in _BILIBILI_QUESTIONS} == {SearchIntent.PLATFORM_BILIBILI}


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

    async def test_single_question_keeps_search_engine_order(self) -> None:
        per_question = {"history of rome": [_doc("qa", r) for r in range(5)]}
        tools = _make_tools()

        with patch.object(tools._searcher, "multi_query_parallel_search", _provider_search(per_question)):
            sources, _ = await tools.fast_search_with_questions(questions=["history of rome"], top_k=3)

        assert [urlparse(str(s["url"])).hostname for s in sources] == [f"qa-r{r}.example.com" for r in range(3)]

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
class TestNativeCodePathMerge:
    """All questions detected as code intent are answered by GitHub code search."""

    async def test_every_question_keeps_its_share(self) -> None:
        per_query = {
            question: [_github_result(f"org{idx}/repo{rank}", f"symbol_{idx}_{rank}") for rank in range(4)]
            for idx, question in enumerate(_CODE_QUESTIONS)
        }
        tools = _make_tools()

        with patch(_SEARCH_GITHUB_CODE, _native_search(per_query)):
            sources, _ = await tools.fast_search_with_questions(questions=list(_CODE_QUESTIONS), top_k=3)

        assert sorted(str(s["url"]).split("/")[3] for s in sources) == ["org0", "org1", "org2"]

    async def test_blocked_hostnames_apply_to_native_results(self) -> None:
        per_query = {
            _CODE_QUESTIONS[0]: [
                SearchResult(
                    title="blocked mirror",
                    link="https://huggingface.co/spaces/org/demo",
                    snippet="Repository: org/demo\nCode Fragment:\nfn mirrored()",
                ),
                _github_result("tikv/raft-rs", "tick"),
            ]
        }
        tools = _make_tools()

        with patch(_SEARCH_GITHUB_CODE, _native_search(per_query)):
            sources, _ = await tools.fast_search_with_questions(
                questions=[_CODE_QUESTIONS[0]], top_k=5, blocked_hostnames=("huggingface.co",)
            )

        assert [urlparse(str(s["url"])).hostname for s in sources] == ["github.com"]

    async def test_falls_back_to_provider_search_with_intent_overrides(self) -> None:
        question = _CODE_QUESTIONS[0]
        tools = _make_tools()
        provider_search = _provider_search({question: [_doc("qa", 0)]})

        with (
            patch(_SEARCH_GITHUB_CODE, _native_search({})),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            sources, _ = await tools.fast_search_with_questions(questions=[question], top_k=3)

        provider_search.assert_awaited_once()
        queries, _, overrides = provider_search.await_args.args
        assert queries == [question]
        assert overrides == [resolve_search_params(detect_search_intent(question), "searxng")]
        assert len(sources) == 1


@pytest.mark.asyncio
class TestNativeBilibiliPathMerge:
    """All questions routed to Bilibili are answered by the Bilibili API."""

    async def test_every_question_keeps_its_share(self) -> None:
        per_query = {q: [_bilibili_video(idx, rank) for rank in range(4)] for idx, q in enumerate(_BILIBILI_QUESTIONS)}
        tools = _make_tools()

        with patch(_SEARCH_BILIBILI, _native_search(per_query)):
            sources, _ = await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3)

        assert sorted(str(s["url"]).rsplit("/", 1)[1][:3] for s in sources) == ["bv0", "bv1", "bv2"]

    async def test_falls_back_to_site_scoped_provider_search(self) -> None:
        per_question = {f"{q} site:bilibili.com": [_doc(f"q{idx}", 0)] for idx, q in enumerate(_BILIBILI_QUESTIONS)}
        tools = _make_tools()
        provider_search = _provider_search(per_question)

        with (
            patch(_SEARCH_BILIBILI, _native_search({})),
            patch.object(tools._searcher, "multi_query_parallel_search", provider_search),
        ):
            sources, _ = await tools.fast_search_with_questions(questions=list(_BILIBILI_QUESTIONS), top_k=3)

        provider_search.assert_awaited_once()
        queries, _, overrides = provider_search.await_args.args
        assert queries == [f"{q} site:bilibili.com" for q in _BILIBILI_QUESTIONS]
        assert overrides == [None, None, None]
        assert len(sources) == 3
