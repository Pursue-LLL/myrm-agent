"""TaskWorker: bounded concurrency, queue order, settle-once semantics, abort and restart recovery.

Runs the real worker against a real SQLiteTaskStore; only the executors are scripted.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    SQLiteTaskStore,
    Task,
    TaskStatus,
)

import app.tasks.worker as worker_module
from app.tasks.worker import TaskWorker

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class _CounterStub:
    def __init__(self) -> None:
        self.samples: list[dict[str, str]] = []

    def labels(self, **labels: str) -> _CounterStub:
        self.samples.append(labels)
        return self

    def inc(self) -> None:
        return


class _HistogramStub:
    def __init__(self) -> None:
        self.samples: list[tuple[dict[str, str], float]] = []
        self._pending_labels: dict[str, str] | None = None

    def labels(self, **labels: str) -> _HistogramStub:
        self._pending_labels = labels
        return self

    def observe(self, value: float) -> None:
        assert self._pending_labels is not None
        self.samples.append((self._pending_labels, value))


class _ScriptedExecutor:
    """Executes image_generate tasks by running a per-test coroutine."""

    def __init__(self, script: Callable[[Task], Awaitable[object]]) -> None:
        self._script = script
        self.started: list[str] = []

    def can_execute(self, task_type: str) -> bool:
        return task_type == "image_generate"

    async def execute(self, task: Task) -> object:
        self.started.append(task.task_id)
        return await self._script(task)


async def _succeed(task: Task) -> object:
    return {"images": [{"url": f"https://cdn.example/{task.task_id}.png"}]}


async def _new_store(tmp_path: Path) -> SQLiteTaskStore:
    store = SQLiteTaskStore(db_path=str(tmp_path / "tasks.db"))
    await store.initialize()
    return store


async def _enqueue(
    store: SQLiteTaskStore,
    task_id: str,
    *,
    priority: int = 5,
    order: int = 0,
    timeout: int = 300,
    status: TaskStatus = TaskStatus.PENDING,
    task_type: str = "image_generate",
) -> None:
    await store.create_task(
        Task(
            task_id=task_id,
            task_type=task_type,
            user_id="user-1",
            status=status,
            payload={"prompt": task_id},
            priority=priority,
            timeout=timeout,
            created_at=_BASE_TIME + timedelta(seconds=order),
        )
    )


async def _wait_for_status(store: SQLiteTaskStore, task_id: str, status: TaskStatus, timeout: float = 3.0) -> Task:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        task = await store.get_task(task_id)
        if task is not None and task.status == status:
            return task
        if asyncio.get_running_loop().time() > deadline:
            actual = task.status if task else None
            raise AssertionError(f"{task_id} never reached {status} (last seen: {actual})")
        await asyncio.sleep(0.02)


@asynccontextmanager
async def _running(worker: TaskWorker) -> AsyncIterator[None]:
    loop_task = asyncio.create_task(worker.start())
    try:
        yield
    finally:
        await worker.stop()
        await asyncio.wait_for(loop_task, timeout=3.0)


def _recording_worker(
    store: SQLiteTaskStore,
    executor: _ScriptedExecutor,
    events: list[tuple[str, TaskStatus]],
    *,
    max_concurrency: int = 3,
) -> TaskWorker:
    async def _on_status_change(task_id: str, status: TaskStatus, data: dict[str, object] | None) -> None:
        _ = data
        events.append((task_id, status))

    return TaskWorker(store=store, executors=[executor], max_concurrency=max_concurrency, on_status_change=_on_status_change)


async def test_success_settles_once_and_records_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    succeeded = _CounterStub()
    duration = _HistogramStub()
    monkeypatch.setattr(worker_module, "task_succeeded_total", succeeded)
    monkeypatch.setattr(worker_module, "task_duration_seconds", duration)
    store = await _new_store(tmp_path)
    await _enqueue(store, "ok")
    events: list[tuple[str, TaskStatus]] = []
    worker = _recording_worker(store, _ScriptedExecutor(_succeed), events)

    async with _running(worker):
        saved = await _wait_for_status(store, "ok", TaskStatus.SUCCEEDED)

    assert saved.result == {"images": [{"url": "https://cdn.example/ok.png"}]}
    assert saved.progress == 1.0
    assert saved.completed_at is not None
    assert saved.worker_id == "worker-1"
    assert events == [("ok", TaskStatus.RUNNING), ("ok", TaskStatus.SUCCEEDED)]
    assert succeeded.samples == [{"task_type": "image_generate"}]
    assert [labels["status"] for labels, _ in duration.samples] == ["succeeded"]


@pytest.mark.parametrize(
    ("error", "recoverable"),
    [
        (ConnectionError("provider unreachable"), ErrorRecoverability.TRANSIENT),
        (RuntimeError("anything unclassified"), ErrorRecoverability.TRANSIENT),
        (PermissionError("provider rejected the key"), ErrorRecoverability.PERMANENT),
    ],
)
async def test_executor_failure_is_final_and_classified(
    tmp_path: Path, error: Exception, recoverable: ErrorRecoverability, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = _CounterStub()
    monkeypatch.setattr(worker_module, "task_failed_total", failed)
    store = await _new_store(tmp_path)
    await _enqueue(store, "boom")

    async def _raise(task: Task) -> object:
        _ = task
        raise error

    worker = _recording_worker(store, _ScriptedExecutor(_raise), [])

    async with _running(worker):
        saved = await _wait_for_status(store, "boom", TaskStatus.FAILED)

    assert saved.error is not None
    assert saved.error.error_type == type(error).__name__
    assert saved.error.recoverable == recoverable
    assert saved.retry_count == 0
    assert saved.next_retry_at is None
    assert failed.samples == [{"task_type": "image_generate", "error_type": type(error).__name__}]


async def test_timeout_fails_the_task_permanently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    timed_out = _CounterStub()
    monkeypatch.setattr(worker_module, "task_timeout_total", timed_out)
    store = await _new_store(tmp_path)
    await _enqueue(store, "slow", timeout=1)

    async def _hang(task: Task) -> object:
        _ = task
        await asyncio.Event().wait()
        return {}

    worker = _recording_worker(store, _ScriptedExecutor(_hang), [])

    async with _running(worker):
        saved = await _wait_for_status(store, "slow", TaskStatus.FAILED, timeout=4.0)

    assert saved.error is not None
    assert saved.error.error_type == "timeout"
    assert saved.error.recoverable == ErrorRecoverability.PERMANENT
    assert timed_out.samples == [{"task_type": "image_generate"}]


async def test_task_without_executor_fails_permanently(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "orphan-type", task_type="audio_transcribe")
    worker = _recording_worker(store, _ScriptedExecutor(_succeed), [])

    async with _running(worker):
        saved = await _wait_for_status(store, "orphan-type", TaskStatus.FAILED)

    assert saved.error is not None
    assert saved.error.error_type == "no_executor"
    assert saved.error.recoverable == ErrorRecoverability.PERMANENT


async def test_higher_priority_runs_first_then_oldest_first(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "old-normal", priority=5, order=0)
    await _enqueue(store, "new-normal", priority=5, order=1)
    await _enqueue(store, "urgent", priority=9, order=2)
    executor = _ScriptedExecutor(_succeed)
    worker = _recording_worker(store, executor, [], max_concurrency=1)

    async with _running(worker):
        await _wait_for_status(store, "new-normal", TaskStatus.SUCCEEDED)

    assert executor.started == ["urgent", "old-normal", "new-normal"]


async def test_concurrency_cap_is_never_exceeded(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    for index in range(6):
        await _enqueue(store, f"t{index}", order=index)
    active = 0
    peak = 0

    async def _track(task: Task) -> object:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return await _succeed(task)

    worker = _recording_worker(store, _ScriptedExecutor(_track), [], max_concurrency=2)

    async with _running(worker):
        await _wait_for_status(store, "t5", TaskStatus.SUCCEEDED)

    assert peak == 2


async def test_finished_slot_is_refilled_without_waiting_for_the_slowest_task(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "slow", order=0)
    await _enqueue(store, "fast", order=1)
    await _enqueue(store, "next", order=2)
    release_slow = asyncio.Event()

    async def _script(task: Task) -> object:
        if task.task_id == "slow":
            await release_slow.wait()
        return await _succeed(task)

    worker = _recording_worker(store, _ScriptedExecutor(_script), [], max_concurrency=2)

    async with _running(worker):
        await _wait_for_status(store, "next", TaskStatus.SUCCEEDED)
        still_running = await store.get_task("slow")
        release_slow.set()
        await _wait_for_status(store, "slow", TaskStatus.SUCCEEDED)

    assert still_running is not None
    assert still_running.status == TaskStatus.RUNNING


async def test_abort_interrupts_the_run_and_frees_its_slot(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "victim", order=0)
    await _enqueue(store, "after", order=1)
    interrupted = asyncio.Event()

    async def _script(task: Task) -> object:
        if task.task_id == "victim":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                interrupted.set()
                raise
        return await _succeed(task)

    events: list[tuple[str, TaskStatus]] = []
    worker = _recording_worker(store, _ScriptedExecutor(_script), events, max_concurrency=1)

    async with _running(worker):
        await _wait_for_status(store, "victim", TaskStatus.RUNNING)
        # What the cancel endpoint does: write CANCELLED first, then stop the execution.
        cancelled = await store.update_task_if_status(
            "victim", (TaskStatus.RUNNING,), status=TaskStatus.CANCELLED, completed_at=datetime.now(UTC)
        )
        assert cancelled is not None
        assert worker.abort("victim") is True
        await asyncio.wait_for(interrupted.wait(), timeout=2.0)
        await _wait_for_status(store, "after", TaskStatus.SUCCEEDED)

    victim = await store.get_task("victim")
    assert victim is not None
    assert victim.status == TaskStatus.CANCELLED
    assert victim.result is None
    assert ("victim", TaskStatus.SUCCEEDED) not in events
    assert ("victim", TaskStatus.FAILED) not in events


async def test_abort_of_a_task_that_is_not_running_is_a_no_op(tmp_path: Path) -> None:
    worker = _recording_worker(await _new_store(tmp_path), _ScriptedExecutor(_succeed), [])

    assert worker.abort("never-started") is False


async def test_a_late_result_cannot_overwrite_a_cancelled_task(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "late")
    release = asyncio.Event()

    async def _script(task: Task) -> object:
        await release.wait()
        return await _succeed(task)

    events: list[tuple[str, TaskStatus]] = []
    executor = _ScriptedExecutor(_script)
    worker = _recording_worker(store, executor, events)

    async with _running(worker):
        await _wait_for_status(store, "late", TaskStatus.RUNNING)
        cancelled = await store.update_task_if_status(
            "late", (TaskStatus.RUNNING,), status=TaskStatus.CANCELLED, completed_at=datetime.now(UTC)
        )
        assert cancelled is not None
        release.set()
        await asyncio.sleep(0.2)

    saved = await store.get_task("late")
    assert saved is not None
    assert saved.status == TaskStatus.CANCELLED
    assert saved.result is None
    assert events == [("late", TaskStatus.RUNNING)]


async def test_cancelled_pending_task_is_never_claimed(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "cancelled-early", order=0)
    await _enqueue(store, "kept", order=1)
    await store.update_task_if_status(
        "cancelled-early", (TaskStatus.PENDING,), status=TaskStatus.CANCELLED, completed_at=datetime.now(UTC)
    )
    executor = _ScriptedExecutor(_succeed)

    async with _running(_recording_worker(store, executor, [])):
        await _wait_for_status(store, "kept", TaskStatus.SUCCEEDED)

    assert executor.started == ["kept"]


async def test_start_fails_tasks_orphaned_by_the_previous_process_as_retryable(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "orphan", status=TaskStatus.RUNNING, order=0)
    await store.update_task("orphan", worker_id="dead-worker", started_at=_BASE_TIME)
    await _enqueue(store, "fresh", order=1)
    events: list[tuple[str, TaskStatus]] = []
    executor = _ScriptedExecutor(_succeed)

    async with _running(_recording_worker(store, executor, events)):
        await _wait_for_status(store, "fresh", TaskStatus.SUCCEEDED)

    orphan = await store.get_task("orphan")
    assert orphan is not None
    assert orphan.status == TaskStatus.FAILED
    assert orphan.error is not None
    assert orphan.error.error_type == "interrupted"
    assert orphan.error.recoverable == ErrorRecoverability.TRANSIENT
    assert ("orphan", TaskStatus.FAILED) in events
    assert executor.started == ["fresh"]


async def test_stop_marks_in_flight_runs_interrupted(tmp_path: Path) -> None:
    store = await _new_store(tmp_path)
    await _enqueue(store, "mid-flight")

    async def _hang(task: Task) -> object:
        _ = task
        await asyncio.Event().wait()
        return {}

    worker = _recording_worker(store, _ScriptedExecutor(_hang), [])
    loop_task = asyncio.create_task(worker.start())
    await _wait_for_status(store, "mid-flight", TaskStatus.RUNNING)

    await worker.stop()
    await asyncio.wait_for(loop_task, timeout=3.0)

    saved = await store.get_task("mid-flight")
    assert saved is not None
    assert saved.status == TaskStatus.FAILED
    assert saved.error is not None
    assert saved.error.error_type == "interrupted"
    assert saved.error.recoverable == ErrorRecoverability.TRANSIENT
