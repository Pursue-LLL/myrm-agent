"""Tests for KanbanTaskRunner per-workspace write serialization.

Covers four guarantees:
1. Two tasks sharing one workspace run serially (never overlap).
2. Tasks on distinct workspaces run concurrently (no false serialization).
3. A task without a resolved workspace skips locking entirely.
4. The lock is released on exception, and the lock table is pruned.

[INPUT]
- app.services.kanban.task_runner.runner::KanbanTaskRunner (POS: Kanban task execution)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Kanban domain types)

[OUTPUT]
- Verified behavior of ``_workspace_lock``.

[POS]
Unit tests for per-workspace serialization in the Kanban task runner.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.kanban.task_runner.runner import KanbanTaskRunner


def _task(task_id: str) -> KanbanTask:
    return KanbanTask(
        task_id=task_id,
        board_id="board-1",
        title=task_id,
        description="",
        agent_id="agent-1",
    )


async def _enter(lock_ctx):
    return await lock_ctx.__aenter__()


async def _exit(lock_ctx):
    await lock_ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_same_workspace_tasks_serialize():
    """Tasks on the same workspace must not run concurrently."""
    store = AsyncMock()
    runner = KanbanTaskRunner(store)
    workspace = "/tmp/kanban-shared"

    task_a = _task("task-a")
    task_b = _task("task-b")

    ctx_a = runner._workspace_lock(task_a, workspace)
    ctx_b = runner._workspace_lock(task_b, workspace)

    await _enter(ctx_a)
    # Second task must block until the first releases.
    waiter = asyncio.ensure_future(_enter(ctx_b))
    await asyncio.sleep(0.05)
    assert not waiter.done(), "same-workspace task must wait for lock"
    await _exit(ctx_a)
    await waiter
    await _exit(ctx_b)

    assert runner._workspace_locks == {}, "lock table must be pruned after release"


@pytest.mark.asyncio
async def test_distinct_workspaces_run_concurrently():
    """Tasks on different workspaces must not serialize against each other."""
    store = AsyncMock()
    runner = KanbanTaskRunner(store)

    task_a = _task("task-a")
    task_b = _task("task-b")

    ctx_a = runner._workspace_lock(task_a, "/tmp/ws-a")
    ctx_b = runner._workspace_lock(task_b, "/tmp/ws-b")

    await _enter(ctx_a)
    waiter = asyncio.ensure_future(_enter(ctx_b))
    await asyncio.sleep(0.05)
    assert waiter.done(), "distinct workspaces must not block each other"
    await _exit(ctx_b)
    await _exit(ctx_a)


@pytest.mark.asyncio
async def test_none_workspace_skips_lock():
    """A task without a resolved workspace must not acquire any lock."""
    store = AsyncMock()
    runner = KanbanTaskRunner(store)
    task = _task("task-none")

    ctx = runner._workspace_lock(task, None)
    await _enter(ctx)
    await _exit(ctx)

    assert runner._workspace_locks == {}, "None workspace must not create a lock"


@pytest.mark.asyncio
async def test_lock_released_on_exception():
    """The lock must be released when the critical section raises."""
    store = AsyncMock()
    runner = KanbanTaskRunner(store)
    task_a = _task("task-a")
    task_b = _task("task-b")
    workspace = "/tmp/kanban-raise"

    with pytest.raises(RuntimeError):
        async with runner._workspace_lock(task_a, workspace):
            raise RuntimeError("boom")

    # Lock must be released and pruned so a later task can acquire immediately.
    ctx_b = runner._workspace_lock(task_b, workspace)
    await _enter(ctx_b)
    await _exit(ctx_b)

    assert runner._workspace_locks == {}, "lock table must be pruned after release"
