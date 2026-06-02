"""Tests for EventBus dedup and deque optimizations."""

import pytest

from app.services.event.app_event_bus import AppEvent, AppEventType, EventBus


@pytest.fixture
def bus():
    return EventBus(max_backlog=5)


def _make_event(event_type: AppEventType = AppEventType.STATUS, data: dict | None = None) -> AppEvent:
    return AppEvent(event_type=event_type, data=data or {"key": "value"})


class TestEventBusDedup:
    """Consecutive duplicate suppression per topic."""

    def test_identical_events_suppressed(self, bus):
        q = bus.subscribe()
        e1 = _make_event(data={"status": "idle"})
        e2 = _make_event(data={"status": "idle"})

        bus.publish(e1)
        bus.publish(e2)

        assert q.qsize() == 1

    def test_different_data_not_suppressed(self, bus):
        q = bus.subscribe()
        e1 = _make_event(data={"status": "idle"})
        e2 = _make_event(data={"status": "busy"})

        bus.publish(e1)
        bus.publish(e2)

        assert q.qsize() == 2

    def test_different_event_type_not_suppressed(self, bus):
        q = bus.subscribe()
        e1 = _make_event(event_type=AppEventType.STATUS, data={"x": 1})
        e2 = _make_event(event_type=AppEventType.HEALTH_ALERT, data={"x": 1})

        bus.publish(e1)
        bus.publish(e2)

        assert q.qsize() == 2

    def test_same_event_after_different_not_suppressed(self, bus):
        q = bus.subscribe()
        e1 = _make_event(data={"status": "idle"})
        e2 = _make_event(data={"status": "busy"})
        e3 = _make_event(data={"status": "idle"})

        bus.publish(e1)
        bus.publish(e2)
        bus.publish(e3)

        assert q.qsize() == 3

    def test_dedup_is_per_topic(self, bus):
        q1 = bus.subscribe(topic="a")
        q2 = bus.subscribe(topic="b")
        e = _make_event(data={"status": "idle"})

        bus.publish(e, topic="a")
        bus.publish(e, topic="b")

        assert q1.qsize() == 1
        assert q2.qsize() == 1


class TestEventBusDeque:
    """Backlog uses deque with O(1) eviction."""

    def test_backlog_replays_to_new_subscriber(self, bus):
        e1 = _make_event(data={"v": 1})
        e2 = _make_event(data={"v": 2})
        bus.publish(e1)
        bus.publish(e2)

        q = bus.subscribe()
        assert q.qsize() == 2

    def test_backlog_respects_maxlen(self, bus):
        for i in range(10):
            bus.publish(_make_event(data={"v": i}))

        q = bus.subscribe()
        assert q.qsize() == 5  # max_backlog=5

    def test_backlog_independent_per_topic(self, bus):
        bus.publish(_make_event(data={"x": 1}), topic="a")
        bus.publish(_make_event(data={"y": 1}), topic="b")

        qa = bus.subscribe(topic="a")
        qb = bus.subscribe(topic="b")

        assert qa.qsize() == 1
        assert qb.qsize() == 1


def test_memory_operation_event_type_registered() -> None:
    assert AppEventType.MEMORY_OPERATION == "memory_operation"
