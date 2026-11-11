"""``crawl_many`` keeps a slow URL from holding the whole call hostage and never penalises a URL that merely queued.

The real batch scheduler runs. The network call is faked and the clocks are shrunk (straggler limit 0.3 s, per-URL
crawl timeout 0.6 s, unwind grace 0.15 s) so the production ratios hold in milliseconds. Where the engine's own
behaviour matters (coalescing, caches, its crawl timeout) the real ``FetchEngine.crawl`` runs too.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import time
from collections.abc import AsyncIterator
from contextlib import suppress
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
# A real page that outlasts the straggler limit by a wide margin, and a crawl timeout that still lets it finish.
_SLOW_PAGE_S = _SOFT_S * 3
_SLOW_PAGE_CAP_S = _SOFT_S * 8
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


async def drain_detached(engine: FetchEngine) -> None:
    """Wait until every fetch a call stopped waiting for has ended on its own."""
    if engine._detached_fetches:
        await asyncio.wait(set(engine._detached_fetches), timeout=5)
    await asyncio.sleep(0)  # the engine drops finished fetches in a done-callback


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


async def test_straggler_is_given_up_once_a_page_is_in_hand_and_its_fetch_keeps_running(
    engine: FetchEngine, caplog: pytest.LogCaptureFixture
) -> None:
    cancelled = script_crawl(engine, {_FAST: 0.01, _HANG: None})

    started = time.perf_counter()
    with caplog.at_level(logging.WARNING, logger=batch_mixin.logger.name):
        success, failed = await engine.crawl_many([_FAST, _HANG])
    elapsed = time.perf_counter() - started

    assert [url for url, _ in success] == [_FAST]
    assert failed == [(_HANG, None)]
    assert cancelled == []
    assert len(engine._detached_fetches) == 1
    assert _SOFT_S - 0.05 <= elapsed < 5
    assert any(_HANG in record.getMessage() and "stopped waiting" in record.getMessage() for record in caplog.records)


async def test_hung_url_with_no_page_in_hand_is_given_up_after_its_crawl_timeout_plus_the_grace(
    engine: FetchEngine,
) -> None:
    cancelled = script_crawl(engine, {_HANG: None})

    started = time.perf_counter()
    async with asyncio.timeout(5):
        success, failed = await engine.crawl_many([_HANG])
    elapsed = time.perf_counter() - started

    assert success == []
    assert failed == [(_HANG, None)]
    assert cancelled == []
    assert _CRAWL_TIMEOUT_S + _GRACE_S - 0.05 <= elapsed < 5


async def test_a_page_in_hand_never_stretches_the_patience_past_the_hard_limit(
    engine: FetchEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch_mixin, "_STRAGGLER_AFTER_S", 60.0)  # longer than the crawl timeout plus the grace
    script_crawl(engine, {_FAST: 0.01, _HANG: None})

    async with asyncio.timeout(5):
        _, failed = await engine.crawl_many([_FAST, _HANG])

    assert failed == [(_HANG, None)]


async def test_shutdown_cancels_the_fetches_a_call_stopped_waiting_for(engine: FetchEngine) -> None:
    cancelled = script_crawl(engine, {_FAST: 0.01, _HANG: None})
    await engine.crawl_many([_FAST, _HANG])

    await engine.shutdown()

    assert cancelled == [_HANG]
    await asyncio.sleep(0)
    assert engine._detached_fetches == set()


async def test_slow_page_is_kept_while_no_other_page_is_in_hand(engine: FetchEngine) -> None:
    slow = "https://slow.example/page"
    cancelled = script_crawl(engine, {slow: _SOFT_S * 1.5})

    success, failed = await engine.crawl_many([slow])

    assert [url for url, _ in success] == [slow]
    assert failed == []
    assert cancelled == []


async def test_stragglers_are_cut_the_moment_a_late_first_page_arrives(engine: FetchEngine) -> None:
    first, second = "https://first.example/page", "https://second.example/page"
    script_crawl(engine, {first: _SOFT_S * 1.5, second: _SOFT_S * 4})

    success, failed = await engine.crawl_many([first, second])

    assert [url for url, _ in success] == [first]
    assert failed == [(second, None)]
    await drain_detached(engine)


async def test_abandoned_fetch_that_succeeds_still_fills_the_cache(engine: FetchEngine) -> None:
    slow = "https://slow.example/page"
    fetched: list[str] = []

    async def degrade(url: str, **_: object) -> tuple[Document | None, None]:
        fetched.append(url)
        await asyncio.sleep(_SLOW_PAGE_S if url == slow else 0.0)
        return _PAGE, None

    engine._crawl_timeout = _SLOW_PAGE_CAP_S
    engine._crawl_with_degradation = AsyncMock(side_effect=degrade)  # type: ignore[method-assign]

    _, failed = await engine.crawl_many([_FAST, slow])
    await drain_detached(engine)
    later_success, later_failed = await engine.crawl_many([slow])

    assert failed == [(slow, None)]
    assert [url for url, _ in later_success] == [slow]
    assert later_failed == []
    assert fetched.count(slow) == 1  # the later call was served from the cache


async def test_abandoned_fetch_that_times_out_is_still_remembered_as_failed(engine: FetchEngine) -> None:
    async def degrade(url: str, **_: object) -> tuple[Document | None, None]:
        if url == _HANG:
            await asyncio.sleep(3600)
        return _PAGE, None

    engine._crawl_with_degradation = AsyncMock(side_effect=degrade)  # type: ignore[method-assign]

    success, failed = await engine.crawl_many([_FAST, _HANG])
    await drain_detached(engine)  # the fetch ran on until the engine's own timeout ended it

    assert [url for url, _ in success] == [_FAST]
    assert failed == [(_HANG, None)]
    assert engine._fail_cache.contains(normalize_url(_HANG))
    assert engine._pending_requests == {}


async def test_callers_waiting_on_an_abandoned_fetch_still_get_its_page(engine: FetchEngine) -> None:
    slow = "https://slow.example/page"
    fetched: list[str] = []

    async def degrade(url: str, **_: object) -> tuple[Document | None, None]:
        fetched.append(url)
        await asyncio.sleep(_SLOW_PAGE_S if url == slow else 0.0)  # done after the first call stopped waiting
        return _PAGE, None

    engine._crawl_timeout = _SLOW_PAGE_CAP_S
    engine._crawl_with_degradation = AsyncMock(side_effect=degrade)  # type: ignore[method-assign]

    first_call = asyncio.create_task(engine.crawl_many([_FAST, slow]))
    await asyncio.sleep(0.05)
    second_success, second_failed = await engine.crawl_many([slow])  # coalesces on the first call's fetch
    first_success, first_failed = await first_call

    assert [url for url, _ in first_success] == [_FAST]
    assert first_failed == [(slow, None)]
    assert [url for url, _ in second_success] == [slow]
    assert second_failed == []
    assert fetched.count(slow) == 1  # one fetch served both calls; stopping to wait did not restart it


async def test_teardown_leaves_a_fetch_that_is_already_unwinding_alone(
    engine: FetchEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batch_mixin, "_UNWIND_GRACE_S", 60.0)  # only the teardown ends the call, not its own limit
    cancels: list[str] = []
    unwound = asyncio.Event()

    async def stuck_then_slow_cleanup(url: str, **_: object) -> tuple[Document | None, None]:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancels.append(url)  # the engine's own timeout; a second cancel would be the call cutting cleanup short
            await asyncio.sleep(_CRAWL_TIMEOUT_S * 1.5)  # closing the browser page takes a while
            unwound.set()
            raise
        return _PAGE, None

    engine._crawl_with_degradation = AsyncMock(side_effect=stuck_then_slow_cleanup)  # type: ignore[method-assign]

    call = asyncio.create_task(engine.crawl_many([_HANG]))
    await asyncio.sleep(_CRAWL_TIMEOUT_S + _SOFT_S)  # the crawl timeout fired; cleanup is under way
    call.cancel()
    with suppress(asyncio.CancelledError):
        await call

    await asyncio.wait_for(unwound.wait(), timeout=5)
    assert cancels == [_HANG]


async def test_error_of_a_fetch_the_call_stopped_waiting_for_is_consumed(engine: FetchEngine) -> None:
    fail_now = asyncio.Event()

    async def crawl(url: str, **_: object) -> Document | None:
        await fail_now.wait()
        raise RuntimeError("late failure")

    engine.crawl = crawl  # type: ignore[method-assign]
    loop = asyncio.get_running_loop()
    reports: list[str] = []
    loop.set_exception_handler(lambda _loop, context: reports.append(context["message"]))
    try:
        _, failed = await engine.crawl_many([_HANG])  # ends on its own hard limit, with the fetch still running
        fail_now.set()
        await drain_detached(engine)
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
        batch_mixin._STRAGGLER_AFTER_S,
    )

    assert batch_mixin._STRAGGLER_AFTER_S < FetchEngine._DEFAULT_CRAWL_TIMEOUT
    assert worst_wait_s + _POST_FETCH_HEADROOM_S <= get_tool_timeout("web_fetch_tool")
