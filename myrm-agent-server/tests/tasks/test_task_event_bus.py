"""TaskEventBus behavior tests."""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest
from myrm_agent_harness.toolkits.tasks import TaskStatus

import app.tasks.events as events_module
from app.tasks.events import TaskEventBus


class _CounterStub:
    def __init__(self) -> None:
        self.samples: list[dict[str, str]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_CounterStub":
        self._labels = labels
        return self

    def inc(self) -> None:
        self.samples.append(dict(self._labels))


@pytest.mark.asyncio
async def test_emit_enqueues_event_for_subscriber() -> None:
    bus = TaskEventBus()
    queue = bus.subscribe()

    await bus.emit("task-1", TaskStatus.PENDING, {"progress": 0.3})

    event = queue.get_nowait()
    assert event["task_id"] == "task-1"
    assert event["status"] == TaskStatus.PENDING.value
    assert event["progress"] == 0.3
    assert "sync_required" not in event


@pytest.mark.asyncio
async def test_emit_replaces_oldest_event_when_subscriber_queue_full() -> None:
    bus = TaskEventBus()
    queue = bus.subscribe()

    for sequence in range(100):
        await bus.emit("task-1", TaskStatus.PENDING, {"sequence": sequence})

    await bus.emit("task-1", TaskStatus.PENDING, {"sequence": 100})
    assert queue.qsize() == 100

    buffered_events = [queue.get_nowait() for _ in range(queue.qsize())]
    sequences = [int(event["sequence"]) for event in buffered_events]

    assert 0 not in sequences
    assert 100 in sequences

    newest_event = next(event for event in buffered_events if event["sequence"] == 100)
    assert newest_event["sync_required"] is True

    with pytest.raises(asyncio.QueueEmpty):
        queue.get_nowait()


@pytest.mark.asyncio
async def test_emit_records_metrics_when_replacing_oldest_on_queue_full(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted = _CounterStub()
    dropped = _CounterStub()
    replaced = _CounterStub()
    monkeypatch.setattr(events_module, "task_event_emitted_total", emitted)
    monkeypatch.setattr(events_module, "task_event_dropped_total", dropped)
    monkeypatch.setattr(events_module, "task_event_replaced_total", replaced)

    bus = TaskEventBus()
    queue = bus.subscribe()
    for seq in range(100):
        queue.put_nowait({"seed": seq})

    await bus.emit("task-2", TaskStatus.PENDING, {"sequence": 100})

    assert emitted.samples == [{"status": TaskStatus.PENDING.value}]
    assert replaced.samples == [{"status": TaskStatus.PENDING.value}]
    assert dropped.samples == [
        {
            "status": TaskStatus.PENDING.value,
            "reason": "queue_full_drop_oldest",
        }
    ]


@pytest.mark.asyncio
async def test_emit_records_drop_newest_metric_when_queue_replace_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted = _CounterStub()
    dropped = _CounterStub()
    replaced = _CounterStub()
    monkeypatch.setattr(events_module, "task_event_emitted_total", emitted)
    monkeypatch.setattr(events_module, "task_event_dropped_total", dropped)
    monkeypatch.setattr(events_module, "task_event_replaced_total", replaced)

    class _AlwaysFullQueue:
        def put_nowait(self, item: dict[str, object]) -> None:
            _ = item
            raise asyncio.QueueFull

        def get_nowait(self) -> dict[str, object]:
            raise asyncio.QueueEmpty

    bus = TaskEventBus()
    bus._subscribers.add(_AlwaysFullQueue())  # type: ignore[arg-type, attr-defined]

    await bus.emit("task-3", TaskStatus.PENDING, {"sequence": 1})

    assert emitted.samples == []
    assert replaced.samples == []
    drop_counts = Counter((sample["status"], sample["reason"]) for sample in dropped.samples)
    assert drop_counts[(TaskStatus.PENDING.value, "queue_full_drop_oldest")] == 1
    assert drop_counts[(TaskStatus.PENDING.value, "queue_full_drop_newest")] == 1


@pytest.mark.asyncio
async def test_emit_throttles_queue_full_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    warning_messages: list[str] = []

    def _capture_warning(msg: str, *args: object) -> None:
        warning_messages.append(msg % args)

    monkeypatch.setattr(events_module.logger, "warning", _capture_warning)

    now_seconds = 100.0

    def _clock() -> float:
        return now_seconds

    bus = TaskEventBus(queue_full_warning_interval_seconds=10.0, monotonic_clock=_clock)
    queue = bus.subscribe()
    for seq in range(100):
        queue.put_nowait({"seed": seq})

    await bus.emit("task-4", TaskStatus.PENDING, {"sequence": 1})
    await bus.emit("task-4", TaskStatus.PENDING, {"sequence": 2})
    await bus.emit("task-4", TaskStatus.PENDING, {"sequence": 3})
    assert len(warning_messages) == 1

    now_seconds = 111.0
    await bus.emit("task-4", TaskStatus.PENDING, {"sequence": 4})

    assert len(warning_messages) == 2
    assert "suppressed 2 similar warnings" in warning_messages[1]
