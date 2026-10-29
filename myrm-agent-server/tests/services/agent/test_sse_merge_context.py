"""The context the main agent stream runs in while ``merge_stream_with_emitter`` drives it, and what happens to it when the consumer stops.

The main stream sets run-level state (workspace trust, executor, workspace root) in one step and reads it in
the next, and a run the user stops or disconnects from must end without a task left running. Both are
properties of the merge, not of any stream, so they are pinned here with plain async generators.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextvars import ContextVar

import pytest

from app.services.agent.streaming_support.sse_failover_emitter import (
    MODEL_FAILOVER_EVENT_TYPE,
    SSEFailoverEmitter,
    merge_stream_with_emitter,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from tests.support.sse_failover_fixtures import make_failover_event, parse_sse_chunk

_STEP_MARKER: ContextVar[str] = ContextVar("step_marker", default="unset")


def _leftover_tasks() -> set[asyncio.Task[object]]:
    return asyncio.all_tasks() - {asyncio.current_task()}


async def _stream_that_waits_forever(step_cancelled: asyncio.Event) -> AsyncIterator[str]:
    """A main stream whose first step never produces a chunk and records that it was cancelled."""
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        step_cancelled.set()
        raise
    yield "data: never\n\n"


@pytest.mark.asyncio
async def test_merge_keeps_a_context_variable_the_main_stream_set_for_its_later_steps():
    """A run sets its workspace trust in one step and reads it in the next, as it would under a plain ``async for``."""
    seen: list[str] = []

    async def _main() -> AsyncIterator[str]:
        _STEP_MARKER.set("set-in-the-first-step")
        yield "data: a\n\n"
        seen.append(_STEP_MARKER.get())
        yield "data: b\n\n"
        seen.append(_STEP_MARKER.get())

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())

    out = [chunk async for chunk in merge_stream_with_emitter(_main(), emitter)]

    assert out == ["data: a\n\n", "data: b\n\n"]
    assert seen == ["set-in-the-first-step", "set-in-the-first-step"]


@pytest.mark.asyncio
async def test_merge_keeps_the_variable_when_a_failover_chunk_arrives_between_steps():
    release = asyncio.Event()
    seen: list[str] = []

    async def _main() -> AsyncIterator[str]:
        _STEP_MARKER.set("set-before-the-failover")
        yield "data: a\n\n"
        await release.wait()
        seen.append(_STEP_MARKER.get())
        yield "data: b\n\n"

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())

    async def _consume() -> list[str]:
        return [chunk async for chunk in merge_stream_with_emitter(_main(), emitter)]

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.01)
    await emitter.emit_failover(make_failover_event())
    await asyncio.sleep(0.05)
    release.set()
    out = await asyncio.wait_for(consumer, timeout=2.0)

    assert seen == ["set-before-the-failover"]
    assert "data: b\n\n" in out


@pytest.mark.asyncio
async def test_merge_does_not_leak_what_the_main_stream_set_into_its_consumer():
    async def _main() -> AsyncIterator[str]:
        _STEP_MARKER.set("set-inside-the-stream")
        yield "data: a\n\n"

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())

    _ = [chunk async for chunk in merge_stream_with_emitter(_main(), emitter)]

    assert _STEP_MARKER.get() == "unset"


@pytest.mark.asyncio
async def test_merge_shows_the_main_stream_what_the_consumer_set_before_it_started():
    seen: list[str] = []

    async def _main() -> AsyncIterator[str]:
        seen.append(_STEP_MARKER.get())
        yield "data: a\n\n"
        seen.append(_STEP_MARKER.get())

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())

    token = _STEP_MARKER.set("set-by-the-consumer")
    try:
        _ = [chunk async for chunk in merge_stream_with_emitter(_main(), emitter)]
    finally:
        _STEP_MARKER.reset(token)

    assert seen == ["set-by-the-consumer", "set-by-the-consumer"]


@pytest.mark.asyncio
async def test_merge_keeps_concurrent_streams_apart_when_each_sets_its_own_value():
    """Two chats on one event loop, one trusted and one not, never see each other's trust."""
    both_set = asyncio.Barrier(2)
    seen: dict[str, str] = {}

    def _main(name: str) -> AsyncIterator[str]:
        async def _stream() -> AsyncIterator[str]:
            _STEP_MARKER.set(name)
            yield "data: a\n\n"
            await both_set.wait()
            seen[name] = _STEP_MARKER.get()
            yield "data: b\n\n"

        return _stream()

    async def _consume(name: str) -> list[str]:
        emitter = SSEFailoverEmitter(message_id=name, collector=StreamContentCollector())
        return [chunk async for chunk in merge_stream_with_emitter(_main(name), emitter)]

    await asyncio.wait_for(asyncio.gather(_consume("trusted"), _consume("restricted")), timeout=2.0)

    assert seen == {"trusted": "trusted", "restricted": "restricted"}


@pytest.mark.asyncio
async def test_merge_lets_the_main_stream_reset_in_a_later_step_what_it_set_in_an_earlier_one():
    """A run that sets a variable in one step and restores it in a later one (as a ``try/finally`` around its steps does) must not fail."""
    outcome: list[str] = []

    async def _main() -> AsyncIterator[str]:
        token = _STEP_MARKER.set("set-in-the-first-step")
        yield "data: a\n\n"
        _STEP_MARKER.reset(token)
        outcome.append(_STEP_MARKER.get())
        yield "data: b\n\n"

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())

    out = [chunk async for chunk in merge_stream_with_emitter(_main(), emitter)]

    assert out == ["data: a\n\n", "data: b\n\n"]
    assert outcome == ["unset"]


@pytest.mark.asyncio
async def test_merge_surfaces_a_failure_of_a_later_step_and_the_next_merge_is_unaffected():
    async def _failing() -> AsyncIterator[str]:
        _STEP_MARKER.set("set-before-the-failure")
        yield "data: a\n\n"
        raise RuntimeError("provider went away")

    async def _fresh() -> AsyncIterator[str]:
        yield f"data: {_STEP_MARKER.get()}\n\n"

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())
    received: list[str] = []

    with pytest.raises(RuntimeError, match="provider went away"):
        async for chunk in merge_stream_with_emitter(_failing(), emitter):
            received.append(chunk)

    after = [
        chunk
        async for chunk in merge_stream_with_emitter(
            _fresh(), SSEFailoverEmitter(message_id="n", collector=StreamContentCollector())
        )
    ]

    assert received == ["data: a\n\n"]
    assert after == ["data: unset\n\n"]


@pytest.mark.asyncio
async def test_closing_the_merge_while_it_hands_over_a_failover_chunk_cancels_the_step_in_flight():
    step_cancelled = asyncio.Event()
    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())
    merged = merge_stream_with_emitter(_stream_that_waits_forever(step_cancelled), emitter)

    first = asyncio.ensure_future(anext(merged))
    await asyncio.sleep(0.01)
    await emitter.emit_failover(make_failover_event())
    chunk = await asyncio.wait_for(first, timeout=2.0)
    await merged.aclose()

    assert parse_sse_chunk(chunk)["type"] == MODEL_FAILOVER_EVENT_TYPE
    assert step_cancelled.is_set()
    assert _leftover_tasks() == set()


@pytest.mark.asyncio
async def test_cancelling_the_consumer_cancels_the_step_in_flight_and_leaves_no_task_behind():
    """A client that disconnects while the model is thinking cancels the request task that drives the merge."""
    step_cancelled = asyncio.Event()
    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())

    async def _consume() -> None:
        async for _ in merge_stream_with_emitter(_stream_that_waits_forever(step_cancelled), emitter):
            pass

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.01)
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert step_cancelled.is_set()
    assert _leftover_tasks() == set()


@pytest.mark.asyncio
async def test_the_cleanup_of_a_run_the_consumer_disconnects_from_still_sees_what_the_run_set():
    """A stopped run releases its executor and workspace through the variables it set earlier in the same run."""
    cleanup_saw: list[str] = []

    async def _main() -> AsyncIterator[str]:
        _STEP_MARKER.set("set-by-the-run")
        yield "data: a\n\n"
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_saw.append(_STEP_MARKER.get())
        yield "data: never\n\n"

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())
    merged = merge_stream_with_emitter(_main(), emitter)

    assert await anext(merged) == "data: a\n\n"
    waiting_for_the_next_chunk = asyncio.ensure_future(anext(merged))
    await asyncio.sleep(0.01)
    waiting_for_the_next_chunk.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting_for_the_next_chunk

    assert cleanup_saw == ["set-by-the-run"]
    assert _leftover_tasks() == set()


@pytest.mark.asyncio
async def test_closing_the_merge_right_after_a_main_chunk_leaves_no_task_behind():
    async def _main() -> AsyncIterator[str]:
        yield "data: a\n\n"
        await asyncio.Event().wait()
        yield "data: b\n\n"

    emitter = SSEFailoverEmitter(message_id="m", collector=StreamContentCollector())
    merged = merge_stream_with_emitter(_main(), emitter)

    assert await anext(merged) == "data: a\n\n"
    await merged.aclose()

    assert _leftover_tasks() == set()
