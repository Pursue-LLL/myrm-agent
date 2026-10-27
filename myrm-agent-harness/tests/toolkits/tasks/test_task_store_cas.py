"""Compare-and-set writes and priority ordering of the SQLite task store."""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    SQLiteTaskStore,
    Task,
    TaskError,
    TaskFilters,
    TaskStatus,
)


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        yield SQLiteTaskStore(db_path=Path(tmp) / "tasks.db")


async def _create(store: SQLiteTaskStore, task_id: str, status: TaskStatus = TaskStatus.PENDING, **fields) -> Task:
    return await store.create_task(Task(task_id, "image_generate", "user-1", status, {}, **fields))


async def test_applies_when_the_status_matches(store):
    await _create(store, "t1")

    updated = await store.update_task_if_status("t1", {TaskStatus.PENDING}, status=TaskStatus.RUNNING, worker_id="w1")

    assert updated is not None
    assert updated.status is TaskStatus.RUNNING
    assert updated.worker_id == "w1"


async def test_refuses_and_leaves_the_row_alone_when_the_status_differs(store):
    await _create(store, "t1", TaskStatus.CANCELLED)

    lost = await store.update_task_if_status("t1", {TaskStatus.RUNNING}, status=TaskStatus.SUCCEEDED, result={"ok": 1})

    assert lost is None
    row = await store.get_task("t1")
    assert row is not None
    assert row.status is TaskStatus.CANCELLED
    assert row.result is None


async def test_unknown_task_is_a_refusal_not_an_error(store):
    assert await store.update_task_if_status("missing", {TaskStatus.PENDING}, status=TaskStatus.RUNNING) is None


async def test_any_of_several_expected_statuses_matches(store):
    for task_id, status in (("a", TaskStatus.PENDING), ("b", TaskStatus.QUEUED), ("c", TaskStatus.RUNNING)):
        await _create(store, task_id, status)

    active = {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING}
    for task_id in ("a", "b", "c"):
        won = await store.update_task_if_status(task_id, active, status=TaskStatus.CANCELLED)
        assert won is not None
        assert won.status is TaskStatus.CANCELLED


async def test_first_terminal_write_wins_when_two_writers_race(store):
    await _create(store, "t1", TaskStatus.RUNNING)

    cancel = store.update_task_if_status("t1", {TaskStatus.RUNNING}, status=TaskStatus.CANCELLED)
    finish = store.update_task_if_status("t1", {TaskStatus.RUNNING}, status=TaskStatus.SUCCEEDED, result={"ok": 1})
    outcomes = await asyncio.gather(cancel, finish)

    winners = [task for task in outcomes if task is not None]
    assert len(winners) == 1
    row = await store.get_task("t1")
    assert row is not None
    assert row.status is winners[0].status


async def test_terminal_write_clears_a_stale_retry_time_and_stores_the_error(store):
    await _create(store, "t1", TaskStatus.RUNNING, next_retry_at=datetime.now(UTC) + timedelta(minutes=5))
    error = TaskError("interrupted", "Service restarted", ErrorRecoverability.TRANSIENT)

    failed = await store.update_task_if_status("t1", {TaskStatus.RUNNING}, status=TaskStatus.FAILED, error=error)

    assert failed is not None
    assert failed.next_retry_at is None
    assert failed.error is not None
    assert (failed.error.error_type, failed.error.recoverable) == ("interrupted", ErrorRecoverability.TRANSIENT)


async def test_plain_update_task_is_still_unconditional(store):
    await _create(store, "t1", TaskStatus.CANCELLED)

    await store.update_task("t1", status=TaskStatus.SUCCEEDED)

    row = await store.get_task("t1")
    assert row is not None
    assert row.status is TaskStatus.SUCCEEDED


async def test_priority_then_arrival_order_is_what_the_listing_returns(store):
    base = datetime.now(UTC)
    for index, priority in enumerate([5, 5, 9, 5, 1, 9]):
        await _create(store, f"t{index}", priority=priority, created_at=base + timedelta(milliseconds=index))

    listed = await store.list_tasks(
        TaskFilters(status=TaskStatus.PENDING, order_by="priority DESC, created_at ASC", limit=10)
    )

    assert [task.task_id for task in listed] == ["t2", "t5", "t0", "t1", "t3", "t4"]
