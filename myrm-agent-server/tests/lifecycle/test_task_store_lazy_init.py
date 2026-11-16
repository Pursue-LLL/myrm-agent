"""The task store opens on first use, so the tasks API answers before the worker has started.

The worker starts after the first screen has loaded, while the first screen already lists tasks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStore

from app.api.tasks.router import router as tasks_router
from app.config.settings import settings
from app.lifecycle import task_worker


class _RecordingWorker:
    """Stands in for the claim loop: only the store it was built on matters here."""

    def __init__(self, *, store: TaskStore, **_: object) -> None:
        self.store = store

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


async def _no_vault_gc() -> None:
    """Stands in for the endless vault sweep, which a test must not leave running."""


@pytest.fixture(autouse=True)
def _unstarted_task_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The store and worker are process-global: each test starts before either exists and writes under its own state dir."""
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    monkeypatch.setattr(task_worker, "_task_store_instance", None)
    monkeypatch.setattr(task_worker, "_task_worker_instance", None)
    monkeypatch.setattr(task_worker, "_task_worker_loop", None)
    monkeypatch.setattr(task_worker, "TaskWorker", _RecordingWorker)
    monkeypatch.setattr(task_worker, "_start_vault_gc", _no_vault_gc)


async def test_the_tasks_api_answers_before_the_worker_has_started() -> None:
    app = FastAPI()
    app.include_router(tasks_router, prefix="/api/v1/tasks")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/tasks", params={"status": "pending"})

    assert response.status_code == 200
    assert response.json() == {"tasks": [], "total": 0}
    assert task_worker.get_task_worker() is None


async def test_concurrent_first_callers_share_one_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_initialize = SQLiteTaskStore.initialize

    async def yielding_initialize(self: SQLiteTaskStore) -> None:
        await asyncio.sleep(0)
        await original_initialize(self)

    monkeypatch.setattr(SQLiteTaskStore, "initialize", yielding_initialize)

    stores = await asyncio.gather(*(task_worker.ensure_task_store() for _ in range(5)))

    assert all(store is stores[0] for store in stores)
    assert task_worker.get_task_store() is stores[0]
    assert (tmp_path / "tasks.db").is_file()


async def test_the_worker_starts_on_the_store_the_api_already_opened() -> None:
    opened = await task_worker.ensure_task_store()

    worker = await task_worker.start_task_worker()
    try:
        assert isinstance(worker, _RecordingWorker)
        assert worker.store is opened
        assert task_worker.get_task_store() is opened
    finally:
        await task_worker.stop_task_worker()


async def test_starting_the_worker_opens_the_store_when_nothing_has_yet() -> None:
    worker = await task_worker.start_task_worker()
    try:
        assert isinstance(worker, _RecordingWorker)
        assert worker.store is task_worker.get_task_store()
    finally:
        await task_worker.stop_task_worker()


def test_reading_the_store_before_it_is_opened_is_an_error_for_callers_that_degrade() -> None:
    with pytest.raises(RuntimeError, match="Task store not initialized"):
        task_worker.get_task_store()
