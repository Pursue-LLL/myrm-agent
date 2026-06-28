"""Tests for WorkspaceMultiplexer — broadcast, subscribe, and session_status events."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer


@pytest.fixture(autouse=True)
def _reset_singleton():
    WorkspaceMultiplexer._instance = None
    yield
    WorkspaceMultiplexer._instance = None


class TestMultiplexerSingleton:
    def test_get_returns_same_instance(self) -> None:
        a = WorkspaceMultiplexer.get()
        b = WorkspaceMultiplexer.get()
        assert a is b

    def test_reset_creates_new_instance(self) -> None:
        a = WorkspaceMultiplexer.get()
        WorkspaceMultiplexer._instance = None
        b = WorkspaceMultiplexer.get()
        assert a is not b


class TestMultiplexerPublish:
    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self) -> None:
        mux = WorkspaceMultiplexer.get()

        received: list[str] = []

        async def consume():
            async for chunk in mux.subscribe():
                received.append(chunk)
                break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        await mux.publish("chat-1", "msg-1", "data: hello")

        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 1
        assert "multiplex" in received[0]

        lines = received[0].strip().split("\n")
        data_line = next(l for l in lines if l.startswith("data: "))
        payload = json.loads(data_line[len("data: "):])
        assert payload["chat_id"] == "chat-1"
        assert payload["message_id"] == "msg-1"
        assert payload["raw_chunk"] == "data: hello"

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self) -> None:
        mux = WorkspaceMultiplexer.get()

        results: dict[str, list[str]] = {"a": [], "b": []}

        async def consume(key: str):
            async for chunk in mux.subscribe():
                results[key].append(chunk)
                break

        ta = asyncio.create_task(consume("a"))
        tb = asyncio.create_task(consume("b"))
        await asyncio.sleep(0.01)

        await mux.publish("c1", "m1", "data: test\n\n")

        await asyncio.gather(
            asyncio.wait_for(ta, timeout=1.0),
            asyncio.wait_for(tb, timeout=1.0),
        )
        assert len(results["a"]) == 1
        assert len(results["b"]) == 1

    @pytest.mark.asyncio
    async def test_no_subscribers_no_error(self) -> None:
        mux = WorkspaceMultiplexer.get()
        await mux.publish("c1", "m1", "data: lonely\n\n")


class TestMultiplexerSessionStatus:
    @pytest.mark.asyncio
    async def test_session_status_event_format(self) -> None:
        mux = WorkspaceMultiplexer.get()

        received: list[str] = []

        async def consume():
            async for chunk in mux.subscribe():
                received.append(chunk)
                break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        mux.publish_session_status("chat-42", "generating", "general")

        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 1

        raw = received[0]
        assert raw.startswith("event: session_status\n")
        data_line = raw.split("data: ")[1].strip()
        payload = json.loads(data_line)
        assert payload["chat_id"] == "chat-42"
        assert payload["status"] == "generating"
        assert payload["agent_type"] == "general"

    @pytest.mark.asyncio
    async def test_session_status_idle(self) -> None:
        mux = WorkspaceMultiplexer.get()

        received: list[str] = []

        async def consume():
            async for chunk in mux.subscribe():
                received.append(chunk)
                if len(received) >= 2:
                    break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        mux.publish_session_status("chat-1", "generating")
        mux.publish_session_status("chat-1", "idle")

        await asyncio.wait_for(task, timeout=1.0)
        assert len(received) == 2

        statuses = []
        for raw in received:
            data_line = raw.split("data: ")[1].strip()
            statuses.append(json.loads(data_line)["status"])
        assert statuses == ["generating", "idle"]

    @pytest.mark.asyncio
    async def test_session_status_default_agent_type(self) -> None:
        mux = WorkspaceMultiplexer.get()

        received: list[str] = []

        async def consume():
            async for chunk in mux.subscribe():
                received.append(chunk)
                break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        mux.publish_session_status("chat-1", "awaiting_approval")

        await asyncio.wait_for(task, timeout=1.0)
        data_line = received[0].split("data: ")[1].strip()
        payload = json.loads(data_line)
        assert payload["agent_type"] == ""


class TestMultiplexerBroadcastResilience:
    @pytest.mark.asyncio
    async def test_full_queue_discarded(self) -> None:
        mux = WorkspaceMultiplexer.get()

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        mux._subscribers.add(queue)
        queue.put_nowait("filler")

        mux.publish_session_status("chat-1", "generating")
        assert queue.qsize() == 1
        assert queue not in mux._subscribers


class TestMultiplexerSubscribeCleanup:
    @pytest.mark.asyncio
    async def test_cancelled_subscriber_removed(self) -> None:
        mux = WorkspaceMultiplexer.get()

        async def consume():
            async for _ in mux.subscribe():
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        assert len(mux._subscribers) == 1

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert len(mux._subscribers) == 0
