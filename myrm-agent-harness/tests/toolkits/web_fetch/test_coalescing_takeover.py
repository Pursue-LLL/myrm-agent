"""A coalesced fetch survives the cancellation of the caller running it and of the callers waiting on it.

The real ``FetchEngine.crawl`` runs (coalescing, caches, error handling); only the tiered network fetch is faked.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.processing.url_normalizer import normalize_url

_URL = "https://page.example/article"
_PAGE = Document(page_content="page", metadata={})


@pytest.fixture
async def engine() -> AsyncIterator[FetchEngine]:
    # A generous coalescing timeout: finishing sooner than it proves the waiters were woken, not timed out.
    # SSRF policy is not under test; skipping it keeps the fake host from needing a DNS lookup.
    fetch_engine = FetchEngine(coalescing_timeout=5.0, allow_private_networks=True)
    yield fetch_engine
    await fetch_engine.shutdown()


def script_fetches(engine: FetchEngine, *seconds_per_call: float | None) -> AsyncMock:
    """Make the network fetch take the scripted seconds per call (``None``: never finish); later calls are instant."""
    remaining = iter(seconds_per_call)

    async def fetch(url: str, **_: object) -> tuple[Document, None]:
        seconds = next(remaining, 0.0)
        await asyncio.sleep(3600 if seconds is None else seconds)
        return _PAGE, None

    network = AsyncMock(side_effect=fetch)
    engine._crawl_with_degradation = network  # type: ignore[method-assign]
    return network


async def test_waiter_takes_over_when_the_leader_is_cancelled(engine: FetchEngine) -> None:
    network = script_fetches(engine, None)
    leader = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)
    waiter = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)

    leader.cancel()

    page = await asyncio.wait_for(waiter, timeout=2)
    assert page is not None
    assert page.page_content == "page"
    assert network.call_count == 2
    with pytest.raises(asyncio.CancelledError):
        await leader


async def test_waiters_of_a_cancelled_leader_share_one_new_fetch(engine: FetchEngine) -> None:
    network = script_fetches(engine, None, 0.1)
    leader = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)
    waiters = [asyncio.create_task(engine.crawl(_URL)) for _ in range(3)]
    await asyncio.sleep(0.05)

    leader.cancel()

    pages = await asyncio.wait_for(asyncio.gather(*waiters, return_exceptions=True), timeout=2)
    assert all(isinstance(page, Document) and page.page_content == "page" for page in pages)
    assert network.call_count == 2


async def test_cancelling_one_waiter_leaves_the_others_and_the_leader_alone(engine: FetchEngine) -> None:
    network = script_fetches(engine, 0.3)
    leader = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)
    cancelled_waiter = asyncio.create_task(engine.crawl(_URL))
    staying_waiter = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)

    cancelled_waiter.cancel()

    outcomes = await asyncio.wait_for(asyncio.gather(staying_waiter, leader, return_exceptions=True), timeout=2)
    assert all(isinstance(page, Document) and page.page_content == "page" for page in outcomes)
    assert network.call_count == 1
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter


async def test_waiter_timing_out_does_not_cancel_the_others(engine: FetchEngine) -> None:
    engine._coalescing_timeout = 0.3
    script_fetches(engine, 0.45)
    leader = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)
    early_waiter = asyncio.create_task(engine.crawl(_URL))  # gives up at 0.35 s, while the leader is still fetching
    await asyncio.sleep(0.15)
    late_waiter = asyncio.create_task(engine.crawl(_URL))

    outcomes = await asyncio.wait_for(asyncio.gather(early_waiter, late_waiter, leader, return_exceptions=True), 5)

    assert all(isinstance(page, Document) and page.page_content == "page" for page in outcomes)


async def test_cancelled_leader_leaves_nothing_in_flight_and_nothing_remembered_as_failed(engine: FetchEngine) -> None:
    network = script_fetches(engine, None)
    leader = asyncio.create_task(engine.crawl(_URL))
    await asyncio.sleep(0.05)

    leader.cancel()

    with pytest.raises(asyncio.CancelledError):
        await leader
    assert engine._pending_requests == {}
    assert not engine._fail_cache.contains(normalize_url(_URL))
    page = await engine.crawl(_URL)
    assert page is not None
    assert network.call_count == 2
