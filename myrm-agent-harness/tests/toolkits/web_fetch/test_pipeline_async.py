"""ContentPipeline.aprocess: conversion runs off the event loop, serially, on one dedicated thread."""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import ContentPipeline

_ARTICLE = (
    "<html><head><title>Async page</title></head><body><article><h1>Heading</h1>"
    + "".join(
        f"<p>Paragraph {i}: enough readable text to pass the pruning thresholds of the pipeline.</p>" for i in range(20)
    )
    + "</article></body></html>"
)

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="unset")


def _fetch_result(url: str = "https://example.com/a") -> FetchResult:
    return FetchResult(html=_ARTICLE, url=url, status_code=200)


@pytest.mark.asyncio
async def test_aprocess_returns_the_same_document_as_process() -> None:
    pipeline = ContentPipeline()
    expected = pipeline.process(_fetch_result())

    actual = await pipeline.aprocess(_fetch_result())

    assert expected is not None and actual is not None
    assert actual.page_content == expected.page_content
    assert actual.metadata == expected.metadata


@pytest.mark.asyncio
async def test_aprocess_propagates_none_for_unusable_pages() -> None:
    assert await ContentPipeline().aprocess(FetchResult(html="", url="https://example.com", status_code=200)) is None


@pytest.mark.asyncio
async def test_aprocess_passes_max_chars_through() -> None:
    document = await ContentPipeline(use_raw_markdown=True).aprocess(_fetch_result(), max_chars=100)

    assert document is not None
    assert document.metadata["was_truncated"] is True
    assert document.page_content.endswith("[TRUNCATED]")


@pytest.mark.asyncio
async def test_aprocess_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = ContentPipeline()
    threads: list[str] = []

    def record_thread(_fetch_result: FetchResult, _max_chars: int = 0) -> Document:
        threads.append(threading.current_thread().name)
        return Document(page_content="x")

    monkeypatch.setattr(pipeline, "process", record_thread)
    await pipeline.aprocess(_fetch_result())

    assert threads and threads[0] != threading.current_thread().name
    assert threads[0].startswith("web-fetch-convert")


@pytest.mark.asyncio
async def test_event_loop_keeps_ticking_while_a_conversion_is_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = ContentPipeline()

    def busy(_fetch_result: FetchResult, _max_chars: int = 0) -> Document:
        time.sleep(0.4)  # stands in for a CPU-bound conversion
        return Document(page_content="x")

    monkeypatch.setattr(pipeline, "process", busy)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    try:
        await pipeline.aprocess(_fetch_result())
    finally:
        ticker_task.cancel()

    # A blocked loop would have recorded no tick at all; a responsive one records dozens (bound is deliberately lax).
    assert ticks >= 10


@pytest.mark.asyncio
async def test_conversions_are_serialised(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = ContentPipeline()
    running = 0
    peak = 0
    guard = threading.Lock()

    def tracked(_fetch_result: FetchResult, _max_chars: int = 0) -> Document:
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        with guard:
            running -= 1
        return Document(page_content="x")

    monkeypatch.setattr(pipeline, "process", tracked)
    await asyncio.gather(*(pipeline.aprocess(_fetch_result()) for _ in range(6)))

    assert peak == 1


@pytest.mark.asyncio
async def test_cancelled_conversion_that_never_started_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = ContentPipeline()
    started: list[str] = []
    release = threading.Event()

    def blocking(fetch_result: FetchResult, _max_chars: int = 0) -> Document:
        started.append(fetch_result.url)
        if fetch_result.url.endswith("/first"):
            release.wait(timeout=5)
        return Document(page_content="x")

    monkeypatch.setattr(pipeline, "process", blocking)
    first = asyncio.create_task(pipeline.aprocess(_fetch_result("https://example.com/first")))
    while not started:
        await asyncio.sleep(0.005)
    queued = asyncio.create_task(pipeline.aprocess(_fetch_result("https://example.com/queued")))
    await asyncio.sleep(0.02)

    queued.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued
    release.set()
    await first
    await pipeline.aprocess(_fetch_result("https://example.com/last"))

    assert started == ["https://example.com/first", "https://example.com/last"]


@pytest.mark.asyncio
async def test_aprocess_propagates_the_callers_context(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = ContentPipeline()
    seen: list[str] = []

    def read_context(_fetch_result: FetchResult, _max_chars: int = 0) -> Document:
        seen.append(_request_id.get())
        return Document(page_content="x")

    monkeypatch.setattr(pipeline, "process", read_context)
    token = _request_id.set("req-42")
    try:
        await pipeline.aprocess(_fetch_result())
    finally:
        _request_id.reset(token)

    assert seen == ["req-42"]


@pytest.mark.asyncio
async def test_aprocess_surfaces_conversion_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = ContentPipeline()

    def explode(_fetch_result: FetchResult, _max_chars: int = 0) -> Document:
        raise RuntimeError("conversion failed")

    monkeypatch.setattr(pipeline, "process", explode)

    with pytest.raises(RuntimeError, match="conversion failed"):
        await pipeline.aprocess(_fetch_result())
