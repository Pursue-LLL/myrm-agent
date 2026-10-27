"""Tests for the ACP event bus."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.acp.core.event_bus import EventBus
from myrm_agent_harness.toolkits.acp.types import RuntimeEvent, RuntimeEventType, create_event


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self) -> None:
        bus = EventBus()
        received: list[RuntimeEvent] = []
        bus.subscribe(callback=lambda e: received.append(e))
        event = create_event(RuntimeEventType.TEXT_DELTA, "s1", content="hi")
        await bus.emit(event)
        assert len(received) == 1
        assert received[0].data["content"] == "hi"

    @pytest.mark.asyncio
    async def test_event_type_filter(self) -> None:
        bus = EventBus()
        errors: list[RuntimeEvent] = []
        bus.subscribe(callback=lambda e: errors.append(e), event_type=RuntimeEventType.ERROR)
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="hi"))
        await bus.emit(create_event(RuntimeEventType.ERROR, "s1", error="fail"))
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_session_filter(self) -> None:
        bus = EventBus()
        s1_events: list[RuntimeEvent] = []
        bus.subscribe(callback=lambda e: s1_events.append(e), session_id="s1")
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="a"))
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s2", content="b"))
        assert len(s1_events) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[RuntimeEvent] = []
        sub_id = bus.subscribe(callback=lambda e: received.append(e))
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="a"))
        bus.unsubscribe(sub_id)
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="b"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_async_callback(self) -> None:
        bus = EventBus()
        received: list[str] = []

        async def handler(e: RuntimeEvent) -> None:
            received.append(str(e.data.get("content", "")))

        bus.subscribe(callback=handler)
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="async"))
        assert received == ["async"]


class TestEventBusEdgeCases:
    @pytest.mark.asyncio
    async def test_callback_error_does_not_propagate(self) -> None:
        bus = EventBus()

        def bad_callback(e: RuntimeEvent) -> None:
            raise ValueError("callback error")

        bus.subscribe(callback=bad_callback)
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="test"))

    @pytest.mark.asyncio
    async def test_clear_removes_all_subscriptions(self) -> None:
        bus = EventBus()
        received: list[RuntimeEvent] = []
        bus.subscribe(callback=lambda e: received.append(e))
        bus.clear()
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="test"))
        assert received == []

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_is_noop(self) -> None:
        bus = EventBus()
        bus.unsubscribe(999)

    @pytest.mark.asyncio
    async def test_combined_type_and_session_filter(self) -> None:
        bus = EventBus()
        matched: list[RuntimeEvent] = []
        bus.subscribe(
            callback=lambda e: matched.append(e),
            event_type=RuntimeEventType.ERROR,
            session_id="s1",
        )
        await bus.emit(create_event(RuntimeEventType.ERROR, "s1", error="match"))
        await bus.emit(create_event(RuntimeEventType.ERROR, "s2", error="wrong session"))
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="wrong type"))
        assert len(matched) == 1
        assert matched[0].data["error"] == "match"

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self) -> None:
        bus = EventBus()
        r1: list[RuntimeEvent] = []
        r2: list[RuntimeEvent] = []
        bus.subscribe(callback=lambda e: r1.append(e))
        bus.subscribe(callback=lambda e: r2.append(e))
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="broadcast"))
        assert len(r1) == 1
        assert len(r2) == 1

    @pytest.mark.asyncio
    async def test_async_callback_error_does_not_propagate(self) -> None:
        bus = EventBus()

        async def bad_async(e: RuntimeEvent) -> None:
            raise ValueError("async boom")

        bus.subscribe(callback=bad_async)
        await bus.emit(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="test"))
