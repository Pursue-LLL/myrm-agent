"""TaskWorker auto-retry behavior tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    RetryPolicy,
    SQLiteTaskStore,
    Task,
    TaskStatus,
)

import app.tasks.worker as worker_module
from app.tasks.worker import TaskWorker


class _CounterStub:
    def __init__(self) -> None:
        self.samples: list[dict[str, str]] = []

    def labels(self, **labels: str) -> "_CounterStub":
        self.samples.append(labels)
        return self

    def inc(self) -> None:
        return


class _HistogramStub:
    def __init__(self) -> None:
        self.samples: list[tuple[dict[str, str], float]] = []
        self._pending_labels: dict[str, str] | None = None

    def labels(self, **labels: str) -> "_HistogramStub":
        self._pending_labels = labels
        return self

    def observe(self, value: float) -> None:
        assert self._pending_labels is not None
        self.samples.append((self._pending_labels, value))


class _TransientFailingExecutor:
    def can_execute(self, task_type: str) -> bool:
        return task_type == "image_generate"

    async def execute(self, task: Task) -> object:
        raise ConnectionError("simulated transient failure")


class _PermanentFailingExecutor:
    def can_execute(self, task_type: str) -> bool:
        return task_type == "image_generate"

    async def execute(self, task: Task) -> object:
        raise PermissionError("simulated permanent failure")


class _SuccessfulExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def can_execute(self, task_type: str) -> bool:
        return task_type == "image_generate"

    async def execute(self, task: Task) -> object:
        _ = task
        self.calls += 1
        return {"image_urls": ["https://cdn.example/success.png"]}


@pytest.mark.asyncio
async def test_worker_transient_failure_requeues_task_with_datetime_retry(tmp_path: object) -> None:
    db_path = tmp_path / "worker-auto-retry.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-auto-retry",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "transient"},
        retry_policy=RetryPolicy(max_retries=3, base_delay=1.0),
    )
    await store.create_task(task)

    observed_statuses: list[TaskStatus] = []

    async def _on_status_change(task_id: str, status: TaskStatus, data: dict[str, object] | None) -> None:
        _ = (task_id, data)
        observed_statuses.append(status)

    worker = TaskWorker(
        store=store,
        executors=[_TransientFailingExecutor()],
        on_status_change=_on_status_change,
    )

    loaded = await store.get_task(task.task_id)
    assert loaded is not None
    await worker._execute_task(loaded)  # noqa: SLF001 - test internal execution path

    saved = await store.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.PENDING
    assert saved.retry_count == 1
    assert saved.error is None
    assert saved.result is None
    assert saved.progress == 0.0
    assert saved.progress_message is None
    assert saved.started_at is None
    assert saved.completed_at is None
    assert saved.worker_id is None
    assert saved.worker_heartbeat_at is None
    assert saved.cancellation_reason is None
    assert isinstance(saved.metadata.get("last_error"), dict)
    assert saved.metadata["last_error"]["recoverable"] == ErrorRecoverability.TRANSIENT.value
    assert isinstance(saved.next_retry_at, datetime)
    assert saved.next_retry_at > datetime.now(UTC)
    assert observed_statuses == [TaskStatus.RUNNING, TaskStatus.PENDING]


@pytest.mark.asyncio
async def test_worker_permanent_failure_marks_failed_without_retry(tmp_path: object) -> None:
    db_path = tmp_path / "worker-permanent-failure.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-permanent-failure",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "permanent"},
        retry_policy=RetryPolicy(max_retries=3, base_delay=1.0),
        next_retry_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await store.create_task(task)

    observed_statuses: list[TaskStatus] = []

    async def _on_status_change(task_id: str, status: TaskStatus, data: dict[str, object] | None) -> None:
        _ = (task_id, data)
        observed_statuses.append(status)

    worker = TaskWorker(
        store=store,
        executors=[_PermanentFailingExecutor()],
        on_status_change=_on_status_change,
    )

    loaded = await store.get_task(task.task_id)
    assert loaded is not None
    await worker._execute_task(loaded)  # noqa: SLF001 - test internal execution path

    saved = await store.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.FAILED
    assert saved.retry_count == 0
    assert saved.next_retry_at is None
    assert saved.error is not None
    assert saved.error.recoverable == ErrorRecoverability.PERMANENT
    assert observed_statuses == [TaskStatus.RUNNING, TaskStatus.FAILED]


@pytest.mark.asyncio
async def test_worker_transient_failure_with_exhausted_retries_marks_failed(tmp_path: object) -> None:
    db_path = tmp_path / "worker-retry-exhausted.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-retry-exhausted",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "exhausted"},
        retry_count=1,
        retry_policy=RetryPolicy(max_retries=1, base_delay=1.0),
        next_retry_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await store.create_task(task)

    worker = TaskWorker(
        store=store,
        executors=[_TransientFailingExecutor()],
    )

    loaded = await store.get_task(task.task_id)
    assert loaded is not None
    await worker._execute_task(loaded)  # noqa: SLF001 - test internal execution path

    saved = await store.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.FAILED
    assert saved.retry_count == 1
    assert saved.next_retry_at is None
    assert saved.error is not None
    assert saved.error.recoverable == ErrorRecoverability.TRANSIENT


@pytest.mark.asyncio
async def test_worker_run_loop_skips_pending_task_until_retry_time(tmp_path: object) -> None:
    db_path = tmp_path / "worker-future-retry.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-future-retry",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "future retry"},
        next_retry_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    await store.create_task(task)

    executor = _SuccessfulExecutor()
    worker = TaskWorker(store=store, executors=[executor])
    worker_task = asyncio.create_task(worker.start())
    await asyncio.sleep(1.2)
    await worker.stop()
    await asyncio.wait_for(worker_task, timeout=2.0)

    saved = await store.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.PENDING
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_worker_run_loop_executes_pending_task_when_retry_time_due(tmp_path: object) -> None:
    db_path = tmp_path / "worker-due-retry.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-due-retry",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "due retry"},
        next_retry_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await store.create_task(task)

    executor = _SuccessfulExecutor()
    worker = TaskWorker(store=store, executors=[executor])
    worker_task = asyncio.create_task(worker.start())

    deadline = asyncio.get_running_loop().time() + 2.0
    final_task: Task | None = None
    while asyncio.get_running_loop().time() < deadline:
        final_task = await store.get_task(task.task_id)
        if final_task is not None and final_task.status == TaskStatus.SUCCEEDED:
            break
        await asyncio.sleep(0.05)

    await worker.stop()
    await asyncio.wait_for(worker_task, timeout=2.0)

    final_task = await store.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.SUCCEEDED
    assert final_task.next_retry_at is None
    assert executor.calls >= 1


@pytest.mark.asyncio
async def test_worker_success_path_records_task_metrics(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    succeeded_counter = _CounterStub()
    duration_histogram = _HistogramStub()
    monkeypatch.setattr(worker_module, "task_succeeded_total", succeeded_counter)
    monkeypatch.setattr(worker_module, "task_duration_seconds", duration_histogram)

    db_path = tmp_path / "worker-metrics-success.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-metrics-success",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "metrics success"},
    )
    await store.create_task(task)

    worker = TaskWorker(
        store=store,
        executors=[_SuccessfulExecutor()],
    )
    loaded = await store.get_task(task.task_id)
    assert loaded is not None
    await worker._execute_task(loaded)  # noqa: SLF001 - test internal execution path

    assert succeeded_counter.samples == [{"task_type": "image_generate"}]
    assert len(duration_histogram.samples) == 1
    labels, value = duration_histogram.samples[0]
    assert labels["task_type"] == "image_generate"
    assert labels["status"] == TaskStatus.SUCCEEDED.value
    assert value >= 0.0


@pytest.mark.asyncio
async def test_worker_retry_path_records_retry_metric(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    retry_counter = _CounterStub()
    failed_counter = _CounterStub()
    monkeypatch.setattr(worker_module, "task_retry_total", retry_counter)
    monkeypatch.setattr(worker_module, "task_failed_total", failed_counter)

    db_path = tmp_path / "worker-metrics-retry.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    task = Task(
        task_id="worker-metrics-retry",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "metrics retry"},
        retry_policy=RetryPolicy(max_retries=3, base_delay=1.0),
    )
    await store.create_task(task)

    worker = TaskWorker(
        store=store,
        executors=[_TransientFailingExecutor()],
    )
    loaded = await store.get_task(task.task_id)
    assert loaded is not None
    await worker._execute_task(loaded)  # noqa: SLF001 - test internal execution path

    assert retry_counter.samples == [{"task_type": "image_generate"}]
    assert failed_counter.samples == []
