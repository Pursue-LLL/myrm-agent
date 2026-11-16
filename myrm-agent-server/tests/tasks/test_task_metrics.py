"""Task metrics contract: the worker and the event bus move the declared instruments, and a telemetry fault never escapes.

The flows run against the real Prometheus instruments and read them back through the default registry, so a label set that
no longer matches its declaration fails here instead of being swallowed by the best-effort recorders.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, Task, TaskStatus
from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram

import app.tasks.events as events_module
from app.tasks.events import TaskEventBus
from app.tasks.metrics import safe_counter_inc, safe_histogram_observe
from app.tasks.worker import TaskWorker

_PROBE_TASK_TYPE = "metrics_probe"


class _Probe:
    """Reads Prometheus samples relative to the moment it was created, so counts left by earlier tests do not matter."""

    def __init__(self, **series: tuple[str, dict[str, str]]) -> None:
        self._series = series
        self._baseline = self._read()

    def _read(self) -> dict[str, float]:
        return {key: REGISTRY.get_sample_value(name, labels) or 0.0 for key, (name, labels) in self._series.items()}

    def moved(self) -> dict[str, float]:
        now = self._read()
        return {key: now[key] - self._baseline[key] for key in now}

    async def moved_to(self, expected: dict[str, float], timeout: float = 4.0) -> dict[str, float]:
        """Poll until the series moved by *expected* (a settle writes them after the status row), else return what moved."""
        deadline = asyncio.get_running_loop().time() + timeout
        while (moved := self.moved()) != expected and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        return moved


class _ProbeExecutor:
    """Succeeds, raises or hangs depending on the task id."""

    def __init__(self) -> None:
        self.victim_started = asyncio.Event()

    def can_execute(self, task_type: str) -> bool:
        return task_type == _PROBE_TASK_TYPE

    async def execute(self, task: Task) -> object:
        if task.task_id == "boom":
            raise RuntimeError("scripted failure")
        if task.task_id == "victim":
            self.victim_started.set()
        if task.task_id in {"slow", "victim"}:
            await asyncio.Event().wait()
        return {}


class _BrokenCounter:
    """Stands in for an instrument whose update raises."""

    def labels(self, **labels: str) -> _BrokenCounter:
        raise RuntimeError(f"cannot record {labels}")


def test_recorders_update_labelled_and_unlabelled_instruments() -> None:
    registry = CollectorRegistry()
    labelled = Counter("labelled_total", "Labelled counter", ("kind",), registry=registry)
    unlabelled = Counter("unlabelled_total", "Unlabelled counter", registry=registry)
    histogram = Histogram("sample_seconds", "Labelled histogram", ("kind",), registry=registry)

    safe_counter_inc(labelled, kind="a")
    safe_counter_inc(unlabelled)
    safe_histogram_observe(histogram, 0.5, kind="a")

    assert registry.get_sample_value("labelled_total", {"kind": "a"}) == 1.0
    assert registry.get_sample_value("unlabelled_total") == 1.0
    assert registry.get_sample_value("sample_seconds_sum", {"kind": "a"}) == 0.5


def test_recorders_swallow_label_drift_and_an_absent_instrument() -> None:
    registry = CollectorRegistry()
    counter = Counter("drift_total", "Labelled counter", ("kind",), registry=registry)
    histogram = Histogram("drift_seconds", "Labelled histogram", ("kind",), registry=registry)

    safe_counter_inc(counter, other="a")  # a label name that no longer matches the declaration
    safe_counter_inc(counter)  # the labels dropped from a labelled counter
    safe_histogram_observe(histogram, 1.0, other="a")
    safe_counter_inc(cast("Counter", None), kind="a")  # the harness factories return None without prometheus_client
    safe_histogram_observe(cast("Histogram", None), 1.0, kind="a")

    assert registry.get_sample_value("drift_total", {"kind": "a"}) is None
    assert registry.get_sample_value("drift_seconds_count", {"kind": "a"}) is None


async def test_event_bus_moves_the_declared_delivery_counters() -> None:
    status = {"status": TaskStatus.PENDING.value}
    probe = _Probe(
        emitted=("myrm_task_event_emitted_total", status),
        dropped=("myrm_task_event_dropped_total", {**status, "reason": "queue_full_drop_oldest"}),
        replaced=("myrm_task_event_replaced_total", status),
    )
    bus = TaskEventBus()
    queue = bus.subscribe()

    await bus.emit("t-1", TaskStatus.PENDING)  # delivered into the free queue
    while not queue.full():
        queue.put_nowait({})
    await bus.emit("t-2", TaskStatus.PENDING)  # queue full: the oldest event is replaced by the newest

    assert probe.moved() == {"emitted": 2.0, "dropped": 1.0, "replaced": 1.0}


async def test_a_failing_delivery_counter_does_not_evict_a_healthy_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events_module, "task_event_emitted_total", _BrokenCounter())
    bus = TaskEventBus()
    queue = bus.subscribe()

    await bus.emit("t-1", TaskStatus.PENDING)
    await bus.emit("t-2", TaskStatus.PENDING)

    assert [queue.get_nowait()["task_id"], queue.get_nowait()["task_id"]] == ["t-1", "t-2"]


async def test_worker_settlements_move_the_declared_task_instruments(tmp_path: Path) -> None:
    task = {"task_type": _PROBE_TASK_TYPE}
    probe = _Probe(
        succeeded=("myrm_task_succeeded_total", task),
        failed=("myrm_task_failed_total", {**task, "error_type": "RuntimeError"}),
        timed_out=("myrm_task_timeout_total", task),
        timeout_failed=("myrm_task_failed_total", {**task, "error_type": "timeout"}),
        cancelled=("myrm_task_cancelled_total", task),
        succeeded_duration=("myrm_task_duration_seconds_count", {**task, "status": "succeeded"}),
        failed_duration=("myrm_task_duration_seconds_count", {**task, "status": "failed"}),
        cancelled_duration=("myrm_task_duration_seconds_count", {**task, "status": "cancelled"}),
    )
    expected = {
        "succeeded": 1.0,
        "failed": 1.0,
        "timed_out": 1.0,
        "timeout_failed": 1.0,
        "cancelled": 1.0,
        "succeeded_duration": 1.0,
        "failed_duration": 2.0,  # the raising task and the timed-out one
        "cancelled_duration": 1.0,
    }
    store = SQLiteTaskStore(db_path=str(tmp_path / "tasks.db"))
    await store.initialize()
    for task_id, timeout in (("ok", 300), ("boom", 300), ("slow", 1), ("victim", 300)):
        await store.create_task(
            Task(
                task_id=task_id,
                task_type=_PROBE_TASK_TYPE,
                user_id="user-1",
                status=TaskStatus.PENDING,
                payload={},
                timeout=timeout,
            )
        )
    executor = _ProbeExecutor()
    worker = TaskWorker(store=store, executors=[executor], max_concurrency=4)
    loop_task = asyncio.create_task(worker.start())
    try:
        await asyncio.wait_for(executor.victim_started.wait(), timeout=3.0)
        # What the cancel endpoint does: write CANCELLED first, then stop the execution.
        cancelled = await store.update_task_if_status(
            "victim", (TaskStatus.RUNNING,), status=TaskStatus.CANCELLED, completed_at=datetime.now(UTC)
        )
        assert cancelled is not None
        assert worker.abort("victim") is True
        moved = await probe.moved_to(expected)
    finally:
        await worker.stop()
        await asyncio.wait_for(loop_task, timeout=3.0)

    assert moved == expected
