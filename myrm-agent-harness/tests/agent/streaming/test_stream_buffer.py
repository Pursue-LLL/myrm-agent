"""Tests for ResilientStreamBuffer and GlobalStreamRegistry.

Validates that SSE reconnection never produces duplicate or missing events,
which is essential for preventing the "dropped repeated characters" bug
that affects competitors using diff-based streaming.
"""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.agent.streaming.stream_buffer import (
    GlobalStreamRegistry,
    ResilientStreamBuffer,
)


@pytest.fixture
def buffer() -> ResilientStreamBuffer:
    return ResilientStreamBuffer("test-run-1")


class TestResilientStreamBuffer:
    @pytest.mark.asyncio
    async def test_append_and_subscribe_basic(self, buffer: ResilientStreamBuffer) -> None:
        """Events appended before subscribe are all yielded."""
        await buffer.append('data: {"type":"message","data":"Hello"}\n\n')
        await buffer.append('data: {"type":"message","data":" World"}\n\n')
        await buffer.end_stream()

        events = []
        async for event in buffer.subscribe():
            events.append(event)
        assert len(events) == 2
        assert "Hello" in events[0]
        assert "World" in events[1]

    @pytest.mark.asyncio
    async def test_subscribe_after_last_event_id(self, buffer: ResilientStreamBuffer) -> None:
        """Reconnecting with Last-Event-ID only yields events AFTER that ID."""
        payloads = []
        for i in range(5):
            p = await buffer.append(f'data: {{"type":"message","data":"chunk{i}"}}\n\n')
            payloads.append(p)
        await buffer.end_stream()

        # Extract event ID from the 3rd event (index 2)
        # Format: "id: {ts}-{seq}\ndata: ..."
        third_payload = payloads[2]
        event_id = third_payload.split("\n")[0].replace("id: ", "")

        events = []
        async for event in buffer.subscribe(last_event_id=event_id):
            events.append(event)

        # Should get events 3 and 4 (after index 2)
        assert len(events) == 2
        assert "chunk3" in events[0]
        assert "chunk4" in events[1]

    @pytest.mark.asyncio
    async def test_no_duplicate_on_reconnect(self, buffer: ResilientStreamBuffer) -> None:
        """Simulates disconnect/reconnect — no event is duplicated."""
        for i in range(10):
            await buffer.append(f'data: {{"data":"token{i}"}}\n\n')

        # First subscriber reads 5 events then "disconnects"
        seen_ids: list[str] = []
        count = 0
        async for event in buffer.subscribe():
            event_id = event.split("\n")[0].replace("id: ", "")
            seen_ids.append(event_id)
            count += 1
            if count == 5:
                break

        last_seen = seen_ids[-1]

        await buffer.end_stream()

        # Reconnect from last seen
        reconnect_events = []
        async for event in buffer.subscribe(last_event_id=last_seen):
            reconnect_events.append(event)

        assert len(reconnect_events) == 5
        for i, ev in enumerate(reconnect_events):
            assert f"token{i + 5}" in ev

    @pytest.mark.asyncio
    async def test_repeated_content_preserved(self, buffer: ResilientStreamBuffer) -> None:
        """Repeated identical payloads are NOT deduplicated."""
        for _ in range(3):
            await buffer.append('data: {"data":"the "}\n\n')
        await buffer.end_stream()

        events = []
        async for event in buffer.subscribe():
            events.append(event)

        assert len(events) == 3
        for ev in events:
            assert "the " in ev

    @pytest.mark.asyncio
    async def test_sliding_window_eviction(self) -> None:
        """When max_bytes is exceeded, oldest events are evicted."""
        buf = ResilientStreamBuffer("evict-test", max_bytes=200)
        for i in range(20):
            await buf.append(f'data: {{"data":"chunk{i:04d}"}}\n\n')
        await buf.end_stream()

        events = []
        async for event in buf.subscribe():
            events.append(event)

        # Should have fewer than 20 events due to eviction
        assert len(events) < 20
        assert len(events) > 0
        # Last event should be the most recent
        assert "chunk0019" in events[-1]

    @pytest.mark.asyncio
    async def test_non_sse_data_ignored(self, buffer: ResilientStreamBuffer) -> None:
        """Payloads not starting with 'data: ' are rejected."""
        result = await buffer.append("not-sse-data")
        assert result == ""

    @pytest.mark.asyncio
    async def test_subscribe_unknown_last_event_id_replays_all(self, buffer: ResilientStreamBuffer) -> None:
        """Unknown Last-Event-ID replays from the oldest available."""
        await buffer.append('data: {"data":"first"}\n\n')
        await buffer.append('data: {"data":"second"}\n\n')
        await buffer.end_stream()

        events = []
        async for event in buffer.subscribe(last_event_id="nonexistent-id"):
            events.append(event)

        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_slow_consumer_does_not_block_append(self, buffer: ResilientStreamBuffer) -> None:
        """A subscriber suspended at the yield point must not hold the Condition
        lock and stall concurrent appends (hermes 'slow tab pins thread' defect)."""
        await buffer.append('data: {"data":"tok1"}\n\n')

        gen = buffer.subscribe()
        await gen.__anext__()  # suspend the generator exactly at the yield point

        # A concurrent append must acquire the lock without waiting on the
        # suspended consumer. 500ms is far above any legit lock turnover.
        await asyncio.wait_for(buffer.append('data: {"data":"tok2"}\n\n'), timeout=0.5)
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_subscribe_emits_heartbeat_when_idle(self, buffer: ResilientStreamBuffer) -> None:
        """When no event arrives within heartbeat_interval, a heartbeat frame is
        yielded so intermediaries keep the SSE connection alive, and the stream
        continues with real payloads after a later append."""
        await buffer.append('data: {"data":"first"}\n\n')

        gen = buffer.subscribe(heartbeat_interval=0.05)
        saw_heartbeat = False
        received: list[str] = []

        # Read the buffered event plus at least one heartbeat (each wait polls
        # for 50ms of idle before emitting). 6 reads cover the initial event,
        # an idle heartbeat, and the post-append payload below.
        for _ in range(6):
            try:
                item = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
            except StopAsyncIteration:
                break
            received.append(item)
            if item == "event: heartbeat\ndata: null\n\n":
                saw_heartbeat = True
                break

        assert saw_heartbeat, "expected a heartbeat frame after idle wait"

        # The stream stays live after the heartbeat: a new append is delivered.
        await buffer.append('data: {"data":"after-heartbeat"}\n\n')
        item = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        received.append(item)
        assert "after-heartbeat" in item

        await buffer.end_stream()
        await gen.aclose()


class TestMultiSubscriber:
    """Concurrent consumers: an in-flight SSE connection and a refresh/re-attach
    subscriber consume the same buffer independently (frontend attachToChat
    reconnect keeps the old listener alive while the new one catches up)."""

    @pytest.mark.asyncio
    async def test_concurrent_subscribers_each_receive_full_stream(self, buffer: ResilientStreamBuffer) -> None:
        await buffer.append('data: {"data":"tok1"}\n\n')
        await buffer.append('data: {"data":"tok2"}\n\n')

        first = buffer.subscribe()
        second = buffer.subscribe()

        # Both subscribers see the two buffered events from their own cursor.
        assert "tok1" in await asyncio.wait_for(first.__anext__(), timeout=2.0)
        assert "tok2" in await asyncio.wait_for(first.__anext__(), timeout=2.0)
        assert "tok1" in await asyncio.wait_for(second.__anext__(), timeout=2.0)
        assert "tok2" in await asyncio.wait_for(second.__anext__(), timeout=2.0)

        # A live event is delivered to both pending readers (no fan-out loss).
        await buffer.append('data: {"data":"tok3"}\n\n')
        assert "tok3" in await asyncio.wait_for(first.__anext__(), timeout=2.0)
        assert "tok3" in await asyncio.wait_for(second.__anext__(), timeout=2.0)

        await buffer.end_stream()
        await first.aclose()
        await second.aclose()

    @pytest.mark.asyncio
    async def test_end_stream_broadcasts_to_all_subscribers(self, buffer: ResilientStreamBuffer) -> None:
        await buffer.append('data: {"data":"only"}\n\n')
        first = buffer.subscribe()
        second = buffer.subscribe()

        assert "only" in await asyncio.wait_for(first.__anext__(), timeout=2.0)
        assert "only" in await asyncio.wait_for(second.__anext__(), timeout=2.0)

        await buffer.end_stream()

        # Both consumers observe the terminal sentinel instead of hanging.
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(first.__anext__(), timeout=2.0)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(second.__anext__(), timeout=2.0)

        await first.aclose()
        await second.aclose()


class TestGlobalStreamRegistry:
    @pytest.mark.asyncio
    async def test_get_or_create(self) -> None:
        registry = GlobalStreamRegistry()
        buf = await registry.get_or_create("run-1")
        assert isinstance(buf, ResilientStreamBuffer)
        buf2 = await registry.get_or_create("run-1")
        assert buf is buf2

    @pytest.mark.asyncio
    async def test_has_buffer(self) -> None:
        registry = GlobalStreamRegistry()
        assert not await registry.has_buffer("run-2")
        await registry.get_or_create("run-2")
        assert await registry.has_buffer("run-2")

    @pytest.mark.asyncio
    async def test_get_lazy_singleton_init(self) -> None:
        """GlobalStreamRegistry.get() lazily creates the process-wide singleton
        on first call and returns the same instance afterwards."""
        assert GlobalStreamRegistry._instance is None
        first = GlobalStreamRegistry.get()
        assert isinstance(first, GlobalStreamRegistry)
        second = GlobalStreamRegistry.get()
        assert first is second
        GlobalStreamRegistry._instance = None

    @pytest.mark.asyncio
    async def test_remove(self) -> None:
        registry = GlobalStreamRegistry()
        await registry.get_or_create("run-3")
        await registry.remove("run-3")
        assert not await registry.has_buffer("run-3")

    @pytest.mark.asyncio
    async def test_get_or_create_hands_a_finished_run_back_for_replay(self) -> None:
        """A client reattaching to a finished run is served that run's buffer, ended and replaying."""
        registry = GlobalStreamRegistry()
        first = await registry.start_run("run-4")
        await first.append('data: {"type":"message","data":"first"}\n\n')
        await first.end_stream()

        reattached = await registry.get_or_create("run-4")

        assert reattached is first
        assert len([event async for event in reattached.subscribe()]) == 1


class TestStartRun:
    """A run resuming under the id of a finished one (an approved tool call) streams its own events."""

    @pytest.mark.asyncio
    async def test_a_new_run_streams_only_its_own_events(self) -> None:
        registry = GlobalStreamRegistry()
        finished = await registry.start_run("run-5")
        await finished.append('data: {"type":"message","data":"asked-for-approval"}\n\n')
        await finished.end_stream()

        resumed = await registry.start_run("run-5")
        reader = asyncio.create_task(_collect(resumed))
        await asyncio.sleep(0)
        await resumed.append('data: {"type":"message","data":"after-approval"}\n\n')
        await resumed.end_stream()
        events = await asyncio.wait_for(reader, timeout=2.0)

        assert resumed is not finished
        assert await registry.get_or_create("run-5") is resumed
        assert len(events) == 1
        assert "after-approval" in events[0]

    @pytest.mark.asyncio
    async def test_the_replaced_run_keeps_streaming_to_its_readers(self) -> None:
        """Replacing a buffer in the registry never cuts a run that has not finished."""
        registry = GlobalStreamRegistry()
        running = await registry.start_run("run-6")
        reader = asyncio.create_task(_collect(running))
        await asyncio.sleep(0)

        await registry.start_run("run-6")
        await running.append('data: {"type":"message","data":"still-running"}\n\n')
        await running.end_stream()
        events = await asyncio.wait_for(reader, timeout=2.0)

        assert len(events) == 1
        assert "still-running" in events[0]

    @pytest.mark.asyncio
    async def test_cleanup_scheduled_for_a_replaced_run_leaves_the_new_run_alone(self) -> None:
        registry = GlobalStreamRegistry()
        finished = await registry.start_run("run-7")
        resumed = await registry.start_run("run-7")
        reader = asyncio.create_task(_collect(resumed))
        await asyncio.sleep(0)

        await registry.remove("run-7", finished)
        await resumed.append('data: {"type":"message","data":"still-streaming"}\n\n')
        await resumed.end_stream()
        events = await asyncio.wait_for(reader, timeout=2.0)

        assert await registry.has_buffer("run-7")
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_cleanup_of_the_current_run_removes_it(self) -> None:
        registry = GlobalStreamRegistry()
        current = await registry.start_run("run-8")

        await registry.remove("run-8", current)

        assert not await registry.has_buffer("run-8")


async def _collect(buffer: ResilientStreamBuffer) -> list[str]:
    return [event async for event in buffer.subscribe()]
