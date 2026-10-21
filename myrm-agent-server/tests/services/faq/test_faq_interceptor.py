"""Unit tests for FAQ semantic interceptor."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.faq.interceptor import FaqInterceptor, FaqMatchResult


def _make_corpus(
    enabled: bool = True,
    threshold: float = 0.85,
    min_score_gap: float = 0.15,
) -> MagicMock:
    c = MagicMock()
    c.id = "corpus-1"
    c.agent_id = "agent-1"
    c.enabled = enabled
    c.threshold = threshold
    c.min_score_gap = min_score_gap
    return c


def _make_entry(entry_id: str = "e-1") -> MagicMock:
    e = MagicMock()
    e.id = entry_id
    e.corpus_id = "corpus-1"
    e.question = "How to reset password?"
    e.answer = "Go to Settings > Security."
    return e


def _make_search_result(score: float, entry_id: str = "e-1") -> MagicMock:
    r = MagicMock()
    r.score = score
    r.document = MagicMock()
    r.document.id = entry_id
    r.document.metadata = {"entry_id": entry_id}
    return r


@asynccontextmanager
async def _mock_session(ret):
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = ret
    session.execute.return_value = result_mock
    yield session


@pytest.fixture
def embedding() -> AsyncMock:
    e = AsyncMock()
    e.embed.return_value = [0.1] * 768
    return e


@pytest.fixture
def vector() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def interceptor(embedding: AsyncMock, vector: AsyncMock) -> FaqInterceptor:
    return FaqInterceptor(embedding, vector)


@pytest.mark.asyncio
async def test_empty_query_returns_none(interceptor: FaqInterceptor) -> None:
    match, corpus_id, score = await interceptor.try_match("agent-1", "  ")
    assert match is None
    assert corpus_id is None
    assert score == 0.0


@pytest.mark.asyncio
async def test_long_query_returns_none(interceptor: FaqInterceptor) -> None:
    match, corpus_id, score = await interceptor.try_match("agent-1", "x" * 501)
    assert match is None
    assert corpus_id is None
    assert score == 0.0


@pytest.mark.asyncio
async def test_no_corpus_returns_none(interceptor: FaqInterceptor) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(None),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None
    assert corpus_id is None


@pytest.mark.asyncio
async def test_disabled_corpus_returns_none(interceptor: FaqInterceptor) -> None:
    corpus = _make_corpus(enabled=False)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(corpus),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None


@pytest.mark.asyncio
async def test_collection_not_exists_returns_none(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus()
    vector.collection_exists.return_value = False

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(corpus),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None
    assert corpus_id == "corpus-1"


@pytest.mark.asyncio
async def test_no_search_results_returns_none(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus()
    vector.collection_exists.return_value = True
    vector.search.return_value = []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(corpus),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None
    assert corpus_id == "corpus-1"
    assert score == 0.0


@pytest.mark.asyncio
async def test_score_below_threshold_returns_none(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus(threshold=0.90)
    vector.collection_exists.return_value = True
    vector.search.return_value = [_make_search_result(0.80)]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(corpus),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None
    assert score == 0.80


@pytest.mark.asyncio
async def test_score_gap_too_small_returns_none(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus(threshold=0.80, min_score_gap=0.15)
    vector.collection_exists.return_value = True
    vector.search.return_value = [
        _make_search_result(0.90, "e-1"),
        _make_search_result(0.88, "e-2"),
    ]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(corpus),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None
    assert score == 0.90


@pytest.mark.asyncio
async def test_successful_match_returns_result(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus(threshold=0.80, min_score_gap=0.10)
    entry = _make_entry()
    vector.collection_exists.return_value = True
    vector.search.return_value = [
        _make_search_result(0.95, "e-1"),
        _make_search_result(0.70, "e-2"),
    ]

    call_count = 0

    @asynccontextmanager
    async def session_factory():
        nonlocal call_count
        session = AsyncMock()
        result_mock = MagicMock()
        if call_count == 0:
            result_mock.scalar_one_or_none.return_value = corpus
        else:
            result_mock.scalar_one_or_none.return_value = entry
        call_count += 1
        session.execute.return_value = result_mock
        yield session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            session_factory,
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "reset password")

    assert match is not None
    assert isinstance(match, FaqMatchResult)
    assert match.entry_id == "e-1"
    assert match.score == 0.95
    assert match.score_gap == pytest.approx(0.25)
    assert match.answer == "Go to Settings > Security."


@pytest.mark.asyncio
async def test_single_result_gap_defaults_to_1(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus(threshold=0.80, min_score_gap=0.10)
    entry = _make_entry()
    vector.collection_exists.return_value = True
    vector.search.return_value = [_make_search_result(0.95, "e-1")]

    call_count = 0

    @asynccontextmanager
    async def session_factory():
        nonlocal call_count
        session = AsyncMock()
        result_mock = MagicMock()
        if call_count == 0:
            result_mock.scalar_one_or_none.return_value = corpus
        else:
            result_mock.scalar_one_or_none.return_value = entry
        call_count += 1
        session.execute.return_value = result_mock
        yield session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            session_factory,
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "reset password")

    assert match is not None
    assert match.score_gap == 1.0


@pytest.mark.asyncio
async def test_entry_not_found_after_vector_match_returns_none(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus(threshold=0.80, min_score_gap=0.10)
    vector.collection_exists.return_value = True
    vector.search.return_value = [
        _make_search_result(0.95, "e-ghost"),
        _make_search_result(0.70, "e-2"),
    ]

    call_count = 0

    @asynccontextmanager
    async def session_factory():
        nonlocal call_count
        session = AsyncMock()
        result_mock = MagicMock()
        if call_count == 0:
            result_mock.scalar_one_or_none.return_value = corpus
        else:
            result_mock.scalar_one_or_none.return_value = None
        call_count += 1
        session.execute.return_value = result_mock
        yield session

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            session_factory,
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "reset password")

    assert match is None
    assert score == 0.95


@pytest.mark.asyncio
async def test_vector_check_exception_returns_none(
    interceptor: FaqInterceptor,
    vector: AsyncMock,
) -> None:
    corpus = _make_corpus()
    vector.collection_exists.side_effect = RuntimeError("connection refused")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.interceptor.get_session",
            lambda: _mock_session(corpus),
        )
        match, corpus_id, score = await interceptor.try_match("agent-1", "How?")

    assert match is None
    assert corpus_id == "corpus-1"
    assert score == 0.0
