"""REST cancel/retry against the real store and worker: first terminal write wins, cancel stops the run."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, Task, TaskFilters, TaskStatus

from app.api.tasks.deps import get_task_store, get_task_worker
from app.api.tasks.router import router as tasks_router
from app.tasks.worker import TaskWorker


class _BlockingExecutor:
    """Blocks every image task until released; records whether the run was interrupted."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.interrupted = asyncio.Event()

    def can_execute(self, task_type: str) -> bool:
        return task_type == "image_generate"

    async def execute(self, task: Task) -> object:
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.interrupted.set()
            raise
        return {"images": [{"url": f"https://cdn.example/{task.task_id}.png"}]}


async def _store(tmp_path: Path) -> SQLiteTaskStore:
    store = SQLiteTaskStore(db_path=str(tmp_path / "tasks.db"))
    await store.initialize()
    return store


async def _enqueue(store: SQLiteTaskStore, task_id: str, status: TaskStatus = TaskStatus.PENDING) -> Task:
    task = Task(task_id=task_id, task_type="image_generate", user_id="user-1", status=status, payload={"prompt": task_id})
    await store.create_task(task)
    return task


def _client(store: SQLiteTaskStore, worker: TaskWorker | None) -> AsyncClient:
    app = FastAPI()
    app.include_router(tasks_router, prefix="/api/v1/tasks")
    app.dependency_overrides[get_task_store] = lambda: store
    app.dependency_overrides[get_task_worker] = lambda: worker
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@asynccontextmanager
async def _running(worker: TaskWorker) -> AsyncIterator[None]:
    loop_task = asyncio.create_task(worker.start())
    try:
        yield
    finally:
        await worker.stop()
        await asyncio.wait_for(loop_task, timeout=3.0)


async def _wait_for_status(store: SQLiteTaskStore, task_id: str, status: TaskStatus, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while (task := await store.get_task(task_id)) is None or task.status != status:
        assert asyncio.get_running_loop().time() < deadline, f"{task_id} never reached {status}"
        await asyncio.sleep(0.02)


async def test_cancelling_a_running_task_stops_its_execution_for_good(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await _enqueue(store, "running")
    executor = _BlockingExecutor()
    worker = TaskWorker(store=store, executors=[executor])

    async with _running(worker):
        await _wait_for_status(store, "running", TaskStatus.RUNNING)
        with patch("app.api.tasks.router.task_event_bus.emit", new=AsyncMock()) as emit:
            async with _client(store, worker) as client:
                response = await client.post("/api/v1/tasks/running/cancel")
        await asyncio.wait_for(executor.interrupted.wait(), timeout=2.0)
        executor.release.set()
        await asyncio.sleep(0.1)

    assert response.status_code == 200
    emit.assert_awaited_once_with("running", TaskStatus.CANCELLED)
    saved = await store.get_task("running")
    assert saved is not None
    assert saved.status == TaskStatus.CANCELLED
    assert saved.cancellation_reason == "User cancelled"
    assert saved.result is None


async def test_cancelling_a_queued_task_keeps_it_out_of_the_worker(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    await _enqueue(store, "queued")

    async with _client(store, None) as client:
        response = await client.post("/api/v1/tasks/queued/cancel")

    assert response.status_code == 200
    saved = await store.get_task("queued")
    assert saved is not None
    assert saved.status == TaskStatus.CANCELLED
    assert await store.list_tasks(TaskFilters(status=TaskStatus.PENDING)) == []


async def test_cancel_loses_to_a_task_that_already_finished(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    running = await _enqueue(store, "raced", status=TaskStatus.RUNNING)
    await store.update_task_if_status(
        "raced", (TaskStatus.RUNNING,), status=TaskStatus.SUCCEEDED, completed_at=datetime.now(UTC), result={"images": []}
    )

    async def stale_snapshot(task_id: str) -> Task:
        return replace(running, status=TaskStatus.RUNNING)

    with (
        patch.object(store, "get_task", new=stale_snapshot),
        patch("app.api.tasks.router.task_event_bus.emit", new=AsyncMock()) as emit,
    ):
        async with _client(store, None) as client:
            response = await client.post("/api/v1/tasks/raced/cancel")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TASK_ALREADY_COMPLETED"
    emit.assert_not_awaited()
    saved = await store.get_task("raced")
    assert saved is not None
    assert saved.status == TaskStatus.SUCCEEDED
    assert saved.result == {"images": []}


async def test_retry_refuses_a_task_that_is_no_longer_failed(tmp_path: Path) -> None:
    store = await _store(tmp_path)
    failed = await _enqueue(store, "requeued", status=TaskStatus.FAILED)
    await store.update_task_if_status("requeued", (TaskStatus.FAILED,), status=TaskStatus.RUNNING, worker_id="worker-1")

    async def stale_snapshot(task_id: str) -> Task:
        return replace(failed, status=TaskStatus.FAILED)

    with (
        patch.object(store, "get_task", new=stale_snapshot),
        patch("app.api.tasks.router.task_event_bus.emit", new=AsyncMock()) as emit,
    ):
        async with _client(store, None) as client:
            response = await client.post("/api/v1/tasks/requeued/retry")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TASK_NOT_RETRYABLE"
    emit.assert_not_awaited()
    saved = await store.get_task("requeued")
    assert saved is not None
    assert saved.status == TaskStatus.RUNNING
    assert saved.worker_id == "worker-1"
