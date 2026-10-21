"""Unit tests for FAQ hit tracker."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.faq.tracker import FaqHitTracker


@asynccontextmanager
async def _mock_session(session: AsyncMock):
    yield session


@pytest.fixture
def tracker() -> FaqHitTracker:
    return FaqHitTracker()


@pytest.mark.asyncio
async def test_record_hit(tracker: FaqHitTracker) -> None:
    session = AsyncMock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.tracker.get_session",
            lambda: _mock_session(session),
        )
        await tracker.record(
            corpus_id="c-1",
            channel="web",
            user_query="reset password",
            top_score=0.95,
            entry_id="e-1",
            hit=True,
        )

    session.add.assert_called_once()
    session.commit.assert_awaited_once()

    log_obj = session.add.call_args[0][0]
    assert log_obj.corpus_id == "c-1"
    assert log_obj.hit is True
    assert log_obj.entry_id == "e-1"


@pytest.mark.asyncio
async def test_record_miss(tracker: FaqHitTracker) -> None:
    session = AsyncMock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.tracker.get_session",
            lambda: _mock_session(session),
        )
        await tracker.record(
            corpus_id="c-1",
            channel="web",
            user_query="unknown question",
            top_score=0.3,
            hit=False,
        )

    log_obj = session.add.call_args[0][0]
    assert log_obj.hit is False
    assert log_obj.entry_id is None


@pytest.mark.asyncio
async def test_record_swallows_exception(tracker: FaqHitTracker) -> None:
    session = AsyncMock()
    session.commit.side_effect = RuntimeError("db down")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.tracker.get_session",
            lambda: _mock_session(session),
        )
        await tracker.record(
            corpus_id="c-1",
            channel="web",
            user_query="test",
            top_score=0.0,
        )


@pytest.mark.asyncio
async def test_get_stats_uses_provided_session(tracker: FaqHitTracker) -> None:
    session = AsyncMock()

    total_result = MagicMock()
    total_result.scalar.return_value = 100
    hits_result = MagicMock()
    hits_result.scalar.return_value = 75

    session.execute.side_effect = [total_result, hits_result]

    stats = await tracker.get_stats("c-1", db=session)
    assert stats == {"total": 100, "hits": 75, "misses": 25}


@pytest.mark.asyncio
async def test_get_stats_zero_counts(tracker: FaqHitTracker) -> None:
    session = AsyncMock()

    total_result = MagicMock()
    total_result.scalar.return_value = 0
    hits_result = MagicMock()
    hits_result.scalar.return_value = 0

    session.execute.side_effect = [total_result, hits_result]

    stats = await tracker.get_stats("c-1", db=session)
    assert stats == {"total": 0, "hits": 0, "misses": 0}


@pytest.mark.asyncio
async def test_list_unmatched_returns_formatted(tracker: FaqHitTracker) -> None:
    session = AsyncMock()
    now = datetime.now(tz=timezone.utc)

    row = MagicMock()
    row.user_query = "strange question"
    row.top_score = 0.42
    row.created_at = now

    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([row])
    session.execute.return_value = result_mock

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.tracker.get_session",
            lambda: _mock_session(session),
        )
        items = await tracker.list_unmatched("c-1", limit=10)

    assert len(items) == 1
    assert items[0]["query"] == "strange question"
    assert items[0]["top_score"] == 0.42


@pytest.mark.asyncio
async def test_list_unmatched_empty(tracker: FaqHitTracker) -> None:
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.__iter__ = lambda self: iter([])
    session.execute.return_value = result_mock

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.faq.tracker.get_session",
            lambda: _mock_session(session),
        )
        items = await tracker.list_unmatched("c-1")

    assert items == []
