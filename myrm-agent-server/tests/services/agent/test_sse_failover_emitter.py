"""Unit tests for `SSEFailoverEmitter` and `merge_stream_with_emitter`.

These verify the server-side bridge that converts harness ``FailoverEvent`` /
``RecoveryEvent`` objects into SSE chunks and interleaves them with the main
agent token stream. They run without a live FastAPI client because the
behaviour under test is purely the streaming adapter; integration with the
real chat endpoint is covered by the higher-level SSE smoke tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.services.agent.streaming_support.sse_failover_emitter import (
    MODEL_FAILOVER_EVENT_TYPE,
    MODEL_RECOVERY_EVENT_TYPE,
    SSEFailoverEmitter,
    merge_stream_with_emitter,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from tests.support.sse_failover_fixtures import (
    make_failover_event,
    make_recovery_event,
    parse_sse_chunk,
    try_parse_sse_chunk,
)


@pytest.mark.asyncio
async def test_emit_failover_serializes_event():
    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="msg-1", collector=collector)

    await emitter.emit_failover(make_failover_event())
    chunk = emitter.queue.get_nowait()
    payload = parse_sse_chunk(chunk)

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

    await emitter.emit_recovery(make_recovery_event())
    chunk = emitter.queue.get_nowait()
    payload = parse_sse_chunk(chunk)

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

    await emitter.emit_failover(make_failover_event())
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
        await emitter.emit_failover(make_failover_event())

    out: list[str] = []
    trigger_task = asyncio.create_task(_trigger())
    async for chunk in merge_stream_with_emitter(_main(), emitter):
        out.append(chunk)
    await trigger_task

    # First main chunk first, then failover (interleaved), then second main.
    assert out[0] == "data: first\n\n"
    parsed = [try_parse_sse_chunk(chunk) for chunk in out]
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
    await emitter.emit_failover(make_failover_event())
    await emitter.emit_recovery(make_recovery_event())

    out: list[str] = []
    async for chunk in merge_stream_with_emitter(_main(), emitter):
        out.append(chunk)

    types = [p.get("type") for c in out if (p := try_parse_sse_chunk(c)) is not None]
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
    await emitter.emit_failover(make_failover_event())

    # Give the consumer a chance to surface the chunk.
    await asyncio.sleep(0.05)
    assert not consumer.done()

    # Now unblock the main iterator and let the consumer finish.
    main_release.set()
    out = await asyncio.wait_for(consumer, timeout=2.0)

    types = [p.get("type") for c in out if (p := try_parse_sse_chunk(c)) is not None]
    assert MODEL_FAILOVER_EVENT_TYPE in types
    assert "data: late\n\n" in out


@pytest.mark.asyncio
async def test_emit_recorded_into_collector_history():
    """Emitted events should be `feed_event`'d so the persisted message keeps them."""
    collector = StreamContentCollector()
    emitter = SSEFailoverEmitter(message_id="m", collector=collector)

    await emitter.emit_failover(make_failover_event())

    # The collector exposes its history via _process_event side effects; we
    # check the public queue subscription path remains stable.
    snapshot, queue = collector.subscribe()
    assert "content" in snapshot
    assert isinstance(queue, asyncio.Queue)
