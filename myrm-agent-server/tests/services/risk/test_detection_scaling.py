"""Detection of a long text: its time budget grows with its length, and it is matched without holding the event loop."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.risk import detection
from app.services.risk.detection import MATCH_TIMEOUT_SECONDS, TIMED_OUT_SUMMARY, match_budget
from app.services.risk.ingress import screen_user_text

from .conftest import EngineBuilder

_LOG_LINE = "2026-10-15 12:00:01 INFO worker-3 handled request id=4821 in 12ms status=ok path=/api/v1/items\n"
_SECRET_LINE = "password: Zk9#mango42"


def _log(chars: int) -> str:
    return _LOG_LINE * (chars // len(_LOG_LINE) + 1)


@pytest.mark.parametrize(("length", "seconds"), [(0, MATCH_TIMEOUT_SECONDS), (100_000, MATCH_TIMEOUT_SECONDS), (4_000_000, 2.0)])
def test_budget_is_the_floor_for_short_text_and_grows_with_long_text(length: int, seconds: float) -> None:
    assert match_budget(length) == pytest.approx(seconds)


async def test_a_harmless_long_paste_is_not_held_for_running_out_of_time(
    build_engine: EngineBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a flat budget this paste counts as a hit; with the length-scaled one it is clean."""
    service = await build_engine()
    paste = _log(1_500_000)

    with monkeypatch.context() as flat:
        flat.setattr(detection, "MATCH_TIMEOUT_SECONDS", 0.001)
        flat.setattr(detection, "MATCH_SECONDS_PER_MEGACHAR", 0.0)
        assert service.detect(paste).blocked

    with monkeypatch.context() as scaled:
        scaled.setattr(detection, "MATCH_TIMEOUT_SECONDS", 0.001)
        scaled.setattr(detection, "MATCH_SECONDS_PER_MEGACHAR", 5.0)
        assert not service.detect(paste).blocked


async def test_a_secret_inside_a_long_paste_is_held(build_engine: EngineBuilder) -> None:
    service = await build_engine()

    result = await service.detect_async(_log(2_000_000) + _SECRET_LINE)

    assert result.blocked
    assert all(m.match_summary != TIMED_OUT_SUMMARY for m in result.matches)


async def test_a_long_text_is_matched_on_a_worker_thread_and_a_short_one_in_place(build_engine: EngineBuilder) -> None:
    service = await build_engine()

    with patch.object(detection.asyncio, "to_thread", wraps=asyncio.to_thread) as to_thread:
        short = await service.detect_async(_log(1_000) + _SECRET_LINE)
        assert to_thread.call_count == 0
        long = await service.detect_async(_log(100_000) + _SECRET_LINE)
        assert to_thread.call_count == 1

    assert short.blocked and long.blocked


async def test_the_event_loop_keeps_running_while_a_long_text_is_matched(build_engine: EngineBuilder) -> None:
    service = await build_engine()
    paste = _log(2_000_000)
    longest_stall = 0.0
    stop = asyncio.Event()

    async def heartbeat() -> None:
        nonlocal longest_stall
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.001)
            now = time.perf_counter()
            longest_stall = max(longest_stall, now - last)
            last = now

    ticker = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.02)  # let the heartbeat start ticking before the match begins
    started = time.perf_counter()
    result = await service.detect_async(paste)
    elapsed = time.perf_counter() - started
    await asyncio.sleep(0.02)  # a loop that was held shows as one long gap at the next tick
    stop.set()
    await ticker

    assert not result.blocked
    assert elapsed > 0.3  # the match took long enough for a stalled loop to show
    assert longest_stall < elapsed / 4


async def test_the_gate_holds_a_secret_in_a_long_paste_and_passes_a_clean_one(
    build_engine: EngineBuilder, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    service = await build_engine()
    with (
        patch("app.services.risk.detection.get_detection_service", return_value=service),
        patch("app.platform_utils.get_session_factory", return_value=session_factory),
    ):
        assert await screen_user_text(_log(1_000_000), session_id="chat-1") is None
        held = await screen_user_text(_log(1_000_000) + _SECRET_LINE, session_id="chat-1")

    assert held is not None and held.blocked
