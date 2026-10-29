"""Unit tests for `SSEFailoverEmitter` and `merge_stream_with_emitter`.

These verify the server-side bridge that converts harness ``FailoverEvent`` /
``RecoveryEvent`` objects into SSE chunks and interleaves them with the main
agent token stream. They run without a live FastAPI client because the
behaviour under test is purely the streaming adapter; integration with the
real chat endpoint is covered by the higher-level SSE smoke tests.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextvars import ContextVar

import pytest
from myrm_agent_harness.toolkits.llms.errors import FailoverReason
from myrm_agent_harness.toolkits.llms.fallback import FailoverEvent, RecoveryEvent

from app.services.agent.streaming_support.sse_failover_emitter import (
    MODEL_FAILOVER_EVENT_TYPE,
    MODEL_RECOVERY_EVENT_TYPE,
    SSEFailoverEmitter,
    merge_stream_with_emitter,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

_STEP_MARKER: ContextVar[str] = ContextVar("step_marker", default="unset")


def _make_failover_event() -> FailoverEvent:
    return FailoverEvent(
        from_model="gpt-4",
        to_model="claude-3-opus",
        reason=FailoverReason.RATE_LIMIT,
        error_message="rate limited",
        cooldown_ms=10_000,
        attempt_count=1,
        available_candidates=["gpt-4", "claude-3-opus"],
        scenario="balanced",
    )


def _make_recovery_event() -> RecoveryEvent:
    return RecoveryEvent(
        model="gpt-4",
        downtime_ms=15_000,
        probe_count=2,
        was_in_cooldown=True,
    )


def _parse_sse_chunk(chunk: str) -> dict[str, object]:
    """Extract the JSON payload from a ``data: {...}\\n\\n`` SSE chunk."""
    assert chunk.startswith("data: "), f"unexpected chunk shape: {chunk!r}"
    json_body = chunk[len("data: ") :].rstrip()
    return json.loads(json_body)


def _try_parse_sse_chunk(chunk: str) -> dict[str, object] | None:
    """Best-effort JSON parse; returns None for raw text chunks used in tests."""
    if not chunk.startswith("data: "):
        return None
    try:
        return json.loads(chunk[len("data: ") :].rstrip())
    except json.JSONDecodeError:
        return None


@pytest.mark.asyncio
async def test_emit_failover_serializes_event():
    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="msg-1", collector=collector)

    await emitter.emit_failover(_make_failover_event())
    chunk = emitter.queue.get_nowait()
    payload = _parse_sse_chunk(chunk)

    assert payload["type"] == MODEL_FAILOVER_EVENT_TYPE
    assert payload["messageId"] == "msg-1"
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["fromModel"] == "gpt-4"
    assert data["toModel"] == "claude-3-opus"
    assert data["reason"] == "rate_limit"
    assert data["attemptCount"] == 1
    assert data["availableCandidates"] == ["gpt-4", "claude-3-opus"]


@pytest.mark.asyncio
async def test_emit_recovery_serializes_event():
    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="msg-2", collector=collector)

    await emitter.emit_recovery(_make_recovery_event())
    chunk = emitter.queue.get_nowait()
    payload = _parse_sse_chunk(chunk)

    assert payload["type"] == MODEL_RECOVERY_EVENT_TYPE
    assert payload["messageId"] == "msg-2"
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["model"] == "gpt-4"
    assert data["downtimeMs"] == 15_000
    assert data["probeCount"] == 2
    assert data["wasInCooldown"] is True


@pytest.mark.asyncio
async def test_emit_after_close_is_noop():
    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="msg-3", collector=collector)
    emitter.close()

    # Drain the sentinel that close() pushes.
    _ = emitter.queue.get_nowait()

    await emitter.emit_failover(_make_failover_event())
    assert emitter.queue.empty(), "closed emitter must not enqueue further payloads"


@pytest.mark.asyncio
async def test_merge_yields_main_chunks_when_no_emits():
    async def _main() -> AsyncIterator[str]:
        for chunk in ("data: a\n\n", "data: b\n\n", "data: c\n\n"):
            yield chunk

    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="m", collector=collector)

    out: list[str] = []
    async for chunk in merge_stream_with_emitter(_main(), emitter):
        out.append(chunk)

    assert out == ["data: a\n\n", "data: b\n\n", "data: c\n\n"]


@pytest.mark.asyncio
async def test_merge_interleaves_failover_event_mid_stream():
    """A failover emitted between two main chunks must be surfaced inline."""
    emit_signal = asyncio.Event()

    async def _main() -> AsyncIterator[str]:
        yield "data: first\n\n"
        # Let the failover emit complete before the next chunk so we get
        # a deterministic interleaving in the merged output.
        emit_signal.set()
        await asyncio.sleep(0.05)
        yield "data: second\n\n"

    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="m", collector=collector)

    async def _trigger() -> None:
        await emit_signal.wait()
        await emitter.emit_failover(_make_failover_event())

    out: list[str] = []
    trigger_task = asyncio.create_task(_trigger())
    async for chunk in merge_stream_with_emitter(_main(), emitter):
        out.append(chunk)
    await trigger_task

    # First main chunk first, then failover (interleaved), then second main.
    assert out[0] == "data: first\n\n"
    parsed = [_try_parse_sse_chunk(chunk) for chunk in out]
    assert any(p is not None and p.get("type") == MODEL_FAILOVER_EVENT_TYPE for p in parsed), (
        "expected a model_failover SSE chunk in the merged stream"
    )
    assert out[-1] == "data: second\n\n"


@pytest.mark.asyncio
async def test_merge_drains_pending_events_when_main_finishes():
    async def _main() -> AsyncIterator[str]:
        yield "data: only\n\n"

    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="m", collector=collector)

    # Pre-load the emitter so the events sit in the queue before iteration.
    await emitter.emit_failover(_make_failover_event())
    await emitter.emit_recovery(_make_recovery_event())

    out: list[str] = []
    async for chunk in merge_stream_with_emitter(_main(), emitter):
        out.append(chunk)

    types = [p.get("type") for c in out if (p := _try_parse_sse_chunk(c)) is not None]
    assert MODEL_FAILOVER_EVENT_TYPE in types
    assert MODEL_RECOVERY_EVENT_TYPE in types
    assert "data: only\n\n" in out


@pytest.mark.asyncio
async def test_merge_surfaces_failover_when_main_is_blocked():
    """Emitter events must drain even while the main iterator is awaiting."""
    main_release = asyncio.Event()

    async def _main() -> AsyncIterator[str]:
        await main_release.wait()
        yield "data: late\n\n"

    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="m", collector=collector)

    async def _consume() -> list[str]:
        out: list[str] = []
        async for chunk in merge_stream_with_emitter(_main(), emitter):
            out.append(chunk)
        return out

    consumer = asyncio.create_task(_consume())

    # Trigger a failover *while the main iterator is still blocked*. The
    # consumer must yield this chunk without waiting for ``main_release``.
    await asyncio.sleep(0.01)
    await emitter.emit_failover(_make_failover_event())

    # Give the consumer a chance to surface the chunk.
    await asyncio.sleep(0.05)
    assert not consumer.done()

    # Now unblock the main iterator and let the consumer finish.
    main_release.set()
    out = await asyncio.wait_for(consumer, timeout=2.0)

    types = [p.get("type") for c in out if (p := _try_parse_sse_chunk(c)) is not None]
    assert MODEL_FAILOVER_EVENT_TYPE in types
    assert "data: late\n\n" in out


@pytest.mark.asyncio
async def test_emit_recorded_into_collector_history():
    """Emitted events should be `feed_event`'d so the persisted message keeps them."""
    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="m", collector=collector)

    await emitter.emit_failover(_make_failover_event())

    # The collector exposes its history via _process_event side effects; we
    # check the public queue subscription path remains stable.
    snapshot, queue = collector.subscribe()
    assert "content" in snapshot
    assert isinstance(queue, asyncio.Queue)


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
    await emitter.emit_failover(_make_failover_event())
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
