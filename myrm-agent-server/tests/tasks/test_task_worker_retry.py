"""TaskWorker auto-retry behavior tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    RetryPolicy,
    SQLiteTaskStore,
    Task,
    TaskStatus,
)

from app.tasks.worker import TaskWorker


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
    assert saved.error is not None
    assert saved.error.recoverable == ErrorRecoverability.TRANSIENT
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
