"""``crawl_many`` keeps a slow URL from holding the whole call hostage and never penalises a URL that merely queued.

The real batch scheduler runs. The network call is faked and the clocks are shrunk (straggler limit 0.3 s, per-URL
crawl timeout 0.6 s, unwind grace 0.15 s) so the production ratios hold in milliseconds. Where cancellation semantics
matter, the real ``FetchEngine.crawl`` runs too, with its own per-URL timeout.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import time
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.timeouts import get_tool_timeout
from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine, batch_mixin
from myrm_agent_harness.toolkits.web_fetch.processing.url_normalizer import normalize_url

_PAGE = Document(page_content="page", metadata={})
_FAST = "https://fast.example/page"
_HANG = "https://hang.example/page"
_SOFT_S = 0.3
_GRACE_S = 0.15
_SETTLE_S = 0.3
_CRAWL_TIMEOUT_S = 0.6
# What the tool call still needs after the fetch: extraction, spilling and delivery, on a loaded host.
_POST_FETCH_HEADROOM_S = 10.0


@pytest.fixture
def shrunk_clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(batch_mixin, "_STRAGGLER_AFTER_S", _SOFT_S)
    monkeypatch.setattr(batch_mixin, "_UNWIND_GRACE_S", _GRACE_S)
    monkeypatch.setattr(batch_mixin, "_CANCEL_SETTLE_S", _SETTLE_S)


@pytest.fixture
async def engine(shrunk_clocks: None) -> AsyncIterator[FetchEngine]:
    # SSRF policy is not under test; skipping it keeps the fake hosts from needing a DNS lookup.
    fetch_engine = FetchEngine(crawl_timeout=_CRAWL_TIMEOUT_S, allow_private_networks=True)
    yield fetch_engine
    await fetch_engine.shutdown()


def script_crawl(engine: FetchEngine, seconds_by_url: dict[str, float | None]) -> list[str]:
    """Make ``engine.crawl`` take the scripted seconds (``None``: never finish); return the URLs it saw cancelled."""
    cancelled: list[str] = []

    async def crawl(url: str, **_: object) -> Document | None:
        seconds = seconds_by_url[url]
        try:
            await asyncio.sleep(3600 if seconds is None else seconds)
        except asyncio.CancelledError:
            cancelled.append(url)
            raise
        return _PAGE

    engine.crawl = crawl  # type: ignore[method-assign]
    return cancelled


async def test_fast_batch_returns_in_completion_order_without_touching_any_deadline(engine: FetchEngine) -> None:
    slow = "https://slow.example/page"
    cancelled = script_crawl(engine, {slow: 0.05, _FAST: 0.01})

    started = time.perf_counter()
    success, failed = await engine.crawl_many([slow, _FAST])

    assert [url for url, _ in success] == [_FAST, slow]
    assert failed == []
    assert cancelled == []
    assert time.perf_counter() - started < _SOFT_S


async def test_empty_batch_returns_nothing(engine: FetchEngine) -> None:
    assert await engine.crawl_many([]) == ([], [])


async def test_straggler_is_cancelled_once_a_page_is_in_hand(
    engine: FetchEngine, caplog: pytest.LogCaptureFixture
) -> None:
    cancelled = script_crawl(engine, {_FAST: 0.01, _HANG: None})

    started = time.perf_counter()
    with caplog.at_level(logging.WARNING, logger=batch_mixin.logger.name):
        success, failed = await engine.crawl_many([_FAST, _HANG])
    elapsed = time.perf_counter() - started

    assert [url for url, _ in success] == [_FAST]
    assert failed == [(_HANG, None)]
    assert cancelled == [_HANG]
    assert _SOFT_S - 0.05 <= elapsed < 5
    assert any(_HANG in record.getMessage() and "gave up" in record.getMessage() for record in caplog.records)


async def test_slow_page_is_kept_while_no_other_page_is_in_hand(engine: FetchEngine) -> None:
    slow = "https://slow.example/page"
    cancelled = script_crawl(engine, {slow: _SOFT_S * 1.5})

    success, failed = await engine.crawl_many([slow])

    assert [url for url, _ in success] == [slow]
    assert failed == []
    assert cancelled == []


async def test_stragglers_are_cut_the_moment_a_late_first_page_arrives(engine: FetchEngine) -> None:
    first, second = "https://first.example/page", "https://second.example/page"
    cancelled = script_crawl(engine, {first: _SOFT_S * 1.5, second: _SOFT_S * 2.5})

    success, failed = await engine.crawl_many([first, second])

    assert [url for url, _ in success] == [first]
    assert failed == [(second, None)]
    assert cancelled == [second]


async def test_page_finished_while_a_cancelled_straggler_unwinds_is_kept(engine: FetchEngine) -> None:
    late = "https://late.example/page"

    async def crawl(url: str, **_: object) -> Document | None:
        if url == _HANG:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(_SETTLE_S * 0.8)  # releasing the browser page takes a moment
                raise
        # ``late`` starts once ``_FAST`` frees a slot and is done before the straggler has unwound, but by the time
        # the call looks at it again it has run longer than the straggler limit.
        await asyncio.sleep(0.1 if url == _FAST else _SOFT_S * 0.9)
        return _PAGE

    engine.crawl = crawl  # type: ignore[method-assign]

    success, failed = await engine.crawl_many([_FAST, _HANG, late], max_concurrency=2)

    assert [url for url, _ in success] == [_FAST, late]
    assert failed == [(_HANG, None)]


async def test_cancelled_straggler_is_not_remembered_as_failed(engine: FetchEngine) -> None:
    async def degrade(url: str, **_: object) -> tuple[Document | None, None]:
        if url == _HANG:
            await asyncio.sleep(3600)
        return _PAGE, None

    engine._crawl_with_degradation = AsyncMock(side_effect=degrade)  # type: ignore[method-assign]

    success, failed = await engine.crawl_many([_FAST, _HANG])

    assert [url for url, _ in success] == [_FAST]
    assert failed == [(_HANG, None)]
    assert not engine._fail_cache.contains(normalize_url(_HANG))
    assert engine._pending_requests == {}


async def test_url_unwinding_after_its_own_timeout_is_never_cancelled_again(engine: FetchEngine) -> None:
    cancels: list[str] = []
    unwound = asyncio.Event()

    async def stuck_then_slow_cleanup(url: str, **_: object) -> tuple[Document | None, None]:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancels.append(url)  # the engine's own timeout; a second one would be the batch cutting cleanup short
            await asyncio.sleep(1.5)  # closing the browser page takes a while
            unwound.set()
            raise
        return _PAGE, None

    engine._crawl_with_degradation = AsyncMock(side_effect=stuck_then_slow_cleanup)  # type: ignore[method-assign]

    started = time.perf_counter()
    success, failed = await engine.crawl_many([_HANG])
    elapsed = time.perf_counter() - started

    assert success == []
    assert failed == [(_HANG, None)]
    assert elapsed >= _CRAWL_TIMEOUT_S + _GRACE_S - 0.05
    assert not unwound.is_set()  # the call stopped waiting while the cleanup was still going on
    await asyncio.wait_for(unwound.wait(), timeout=5)
    assert cancels == [_HANG]


async def test_error_of_a_fetch_the_call_stopped_waiting_for_is_consumed(engine: FetchEngine) -> None:
    async def crawl(url: str, **_: object) -> Document | None:
        await asyncio.sleep(_CRAWL_TIMEOUT_S + _GRACE_S * 3)  # fails after the hard limit ended the call
        raise RuntimeError("late failure")

    engine.crawl = crawl  # type: ignore[method-assign]
    loop = asyncio.get_running_loop()
    reports: list[str] = []
    loop.set_exception_handler(lambda _loop, context: reports.append(context["message"]))
    try:
        _, failed = await engine.crawl_many([_HANG])
        await asyncio.sleep(_GRACE_S * 6)
        gc.collect()
    finally:
        loop.set_exception_handler(None)

    assert failed == [(_HANG, None)]
    assert not [message for message in reports if message.startswith("Task exception was never retrieved")]


async def test_urls_waiting_for_a_slot_are_not_given_up_on(
    engine: FetchEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch_mixin, "_STRAGGLER_AFTER_S", 0.5)
    urls = [f"https://queued{index}.example/page" for index in range(6)]
    running = peak = 0

    async def crawl(url: str, **_: object) -> Document | None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.12)  # six in a row take longer than the straggler limit; none of them runs that long
        running -= 1
        return _PAGE

    engine.crawl = crawl  # type: ignore[method-assign]

    success, failed = await engine.crawl_many(urls, max_concurrency=1)

    assert [url for url, _ in success] == urls
    assert failed == []
    assert peak == 1


async def test_unexpected_error_propagates_and_cancels_the_rest(engine: FetchEngine) -> None:
    bad = "https://bad.example/page"
    cancelled: list[str] = []

    async def crawl(url: str, **_: object) -> Document | None:
        if url == bad:
            await asyncio.sleep(0.02)
            raise RuntimeError("boom")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(url)
            raise
        return _PAGE

    engine.crawl = crawl  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        await engine.crawl_many([bad, _HANG])

    assert cancelled == [_HANG]


async def test_outer_cancellation_cancels_every_fetch(engine: FetchEngine) -> None:
    other = "https://other.example/page"
    cancelled = script_crawl(engine, {_HANG: None, other: None})

    call = asyncio.create_task(engine.crawl_many([_HANG, other]))
    await asyncio.sleep(0.05)
    call.cancel()

    with pytest.raises(asyncio.CancelledError):
        await call
    assert sorted(cancelled) == sorted([_HANG, other])


def test_worst_case_wait_leaves_room_before_the_tool_timeout() -> None:
    """A batch holding a hung URL ends well before the executor would kill (and retry) the whole tool call."""
    worst_wait_s = max(
        FetchEngine._DEFAULT_CRAWL_TIMEOUT + batch_mixin._UNWIND_GRACE_S,
        batch_mixin._STRAGGLER_AFTER_S + batch_mixin._CANCEL_SETTLE_S,
    )

    assert batch_mixin._STRAGGLER_AFTER_S < FetchEngine._DEFAULT_CRAWL_TIMEOUT
    assert worst_wait_s + _POST_FETCH_HEADROOM_S <= get_tool_timeout("web_fetch_tool")
