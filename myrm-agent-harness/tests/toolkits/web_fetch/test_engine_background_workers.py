"""Stale-while-revalidate workers exist only once a stale cache entry has work for them.

A tool call in local mode builds a ``FetchEngine`` of its own and never shuts it down. An engine that started its
workers on its first crawl left every one of them idle on an empty queue, and when the engine was collected asyncio
reported each as "Task was destroyed but it is pending!" at ERROR level: ten reports per tool call.
"""

from __future__ import annotations

import asyncio
import gc
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.engine.types import CachedDocument
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import _fetch_full_content

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.session_vault import SessionVault

URL = "https://example.com/page"
WORKERS = 3

_ENTRY_POINTS: dict[str, Callable[[FetchEngine, list[str]], Awaitable[object]]] = {
    "crawl": lambda engine, urls: engine.crawl(urls[0]),
    "crawl_many": lambda engine, urls: engine.crawl_many(urls),
    "prefetch": lambda engine, urls: engine.prefetch(urls),
    "prefetch_with_retry": lambda engine, urls: engine.prefetch_with_retry(urls),
}


def _crawled() -> tuple[Document, FetchResult]:
    return Document(page_content="page body", metadata={"url": URL}), FetchResult(html="<html></html>", url=URL)


def _engine() -> FetchEngine:
    return FetchEngine(allow_private_networks=True, max_background_tasks=WORKERS)


def _worker_tasks() -> list[asyncio.Task[object]]:
    """Every revalidation worker alive on the running loop."""
    return [
        task
        for task in asyncio.all_tasks()
        if getattr(task.get_coro(), "__qualname__", "").endswith("._background_worker")
    ]


@pytest.fixture
async def started_workers() -> Callable[[], list[asyncio.Task[object]]]:
    """Revalidation workers started since the test began; the tests of this module share one event loop."""
    before = set(_worker_tasks())
    return lambda: [task for task in _worker_tasks() if task not in before]


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
async def test_crawling_new_urls_starts_no_workers(
    entry_point: str, started_workers: Callable[[], list[asyncio.Task[object]]]
) -> None:
    engine = _engine()
    urls = [f"https://example.com/{entry_point}/{number}" for number in range(3)]

    with patch.object(engine, "_crawl_with_degradation", AsyncMock(return_value=_crawled())):
        await _ENTRY_POINTS[entry_point](engine, urls)

    assert engine._background_workers == []
    assert started_workers() == []
    assert engine.get_cache_metrics()["background_revalidation"]["active_workers"] == 0
    await engine.shutdown()


async def test_a_stale_hit_starts_the_workers_once_and_a_worker_revalidates_it(
    started_workers: Callable[[], list[asyncio.Task[object]]],
) -> None:
    engine = _engine()
    stale = CachedDocument(doc=_crawled()[0], etag=None, last_modified=None, cached_at=0.0)
    revalidated = asyncio.Event()

    async def revalidate(url: str, cache_key: str, cached_item: CachedDocument) -> None:
        revalidated.set()

    with (
        patch.object(engine._crawl_cache, "get_with_expiry", return_value=(stale, True)),
        patch.object(engine, "_background_revalidate", side_effect=revalidate),
    ):
        assert await engine.crawl(URL) is stale.doc
        assert await engine.crawl(f"{URL}-2") is stale.doc
        assert len(engine._background_workers) == WORKERS
        assert len(started_workers()) == WORKERS
        await asyncio.wait_for(revalidated.wait(), timeout=5)

    await engine.shutdown()
    assert engine._background_workers == []
    assert started_workers() == []


async def test_discarded_engines_leave_nothing_for_asyncio_to_report() -> None:
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    reports: list[str] = []
    loop.set_exception_handler(lambda _loop, context: reports.append(str(context.get("message"))))
    try:
        for _ in range(3):
            engine = _engine()
            with patch.object(engine, "_crawl_with_degradation", AsyncMock(return_value=_crawled())):
                await engine.crawl_many([URL])
            del engine
        gc.collect()
    finally:
        loop.set_exception_handler(previous_handler)

    assert reports == []


class _TrackedEngine(FetchEngine):
    """The engine a tool call builds, remembered so the test can look inside it afterwards."""

    built: ClassVar[list[FetchEngine]] = []

    def __init__(
        self, *, use_raw_markdown: bool, allow_private_networks: bool, session_vault: SessionVault | None
    ) -> None:
        super().__init__(
            use_raw_markdown=use_raw_markdown,
            allow_private_networks=allow_private_networks,
            session_vault=session_vault,
        )
        self.built.append(self)


async def test_the_engines_a_local_mode_tool_call_builds_hold_no_workers(
    monkeypatch: pytest.MonkeyPatch, started_workers: Callable[[], list[asyncio.Task[object]]]
) -> None:
    _TrackedEngine.built.clear()
    monkeypatch.setattr("myrm_agent_harness.toolkits.web_fetch.FetchEngine", _TrackedEngine)
    monkeypatch.setattr(FetchEngine, "_crawl_with_degradation", AsyncMock(return_value=_crawled()))

    for number in range(3):
        await _fetch_full_content([f"{URL}/{number}"], allow_private_networks=True)

    assert len(_TrackedEngine.built) == 3
    assert all(engine._background_workers == [] for engine in _TrackedEngine.built)
    assert started_workers() == []
