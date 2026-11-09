"""Dispatch gate and per-task bookkeeping guard.

The gate decides whether a dispatcher may claim READY tasks at all: without a usable model
configuration nothing can run, so claiming would only write a failure row per task on every boot.
The bookkeeping guard keeps one such failure from escaping as an unretrieved task exception.
"""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        self.calls.append(task.task_id)
        return True, "ok"


class _BrokenStore(InMemoryKanbanStore):
    """Store whose failure bookkeeping write explodes, like a locked SQLite database."""

    async def complete_run(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        raise RuntimeError("database is locked")


def _board() -> KanbanBoard:
    return KanbanBoard(
        board_id="b1",
        name="Board",
        settings=BoardSettings(max_concurrent_tasks=3, heartbeat_interval_seconds=1, zombie_timeout_seconds=60),
    )


def _ready(task_id: str) -> KanbanTask:
    return KanbanTask(
        task_id=task_id,
        board_id="b1",
        title=f"Task {task_id}",
        status=TaskStatus.READY,
        priority=TaskPriority.NORMAL,
    )


@pytest.mark.asyncio
async def test_blocked_gate_leaves_ready_tasks_queued() -> None:
    """A closed gate means no claim at all: the task stays READY and the runner is never called."""
    store = InMemoryKanbanStore()
    board = _board()
    await store.save_board(board)
    await store.save_task(_ready("t1"))
    runner = _RecordingRunner()

    async def never_allowed() -> bool:
        return False

    dispatcher = KanbanDispatcher(store, runner, board, dispatch_allowed=never_allowed)
    await dispatcher.start()
    await asyncio.sleep(0.2)
    await dispatcher.stop()

    task = await store.get_task("t1")
    assert task is not None
    assert task.status == TaskStatus.READY
    assert runner.calls == []


@pytest.mark.asyncio
async def test_open_gate_dispatches_normally() -> None:
    """An open gate keeps the pre-existing behaviour: the READY task is claimed and executed."""
    store = InMemoryKanbanStore()
    board = _board()
    await store.save_board(board)
    await store.save_task(_ready("t1"))
    runner = _RecordingRunner()

    async def allowed() -> bool:
        return True

    dispatcher = KanbanDispatcher(store, runner, board, dispatch_allowed=allowed)
    await dispatcher.start()
    for _ in range(50):
        if runner.calls:
            break
        await asyncio.sleep(0.02)
    await dispatcher.stop()

    assert runner.calls == ["t1"]
    task = await store.get_task("t1")
    assert task is not None
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_gate_reopens_without_restart() -> None:
    """The gate is asked on every wake cycle, so saving a provider resumes queued work."""
    store = InMemoryKanbanStore()
    board = _board()
    await store.save_board(board)
    await store.save_task(_ready("t1"))
    runner = _RecordingRunner()
    state = {"allowed": False}

    async def gate() -> bool:
        return state["allowed"]

    dispatcher = KanbanDispatcher(store, runner, board, dispatch_allowed=gate)
    await dispatcher.start()
    await asyncio.sleep(0.2)
    assert runner.calls == []

    state["allowed"] = True
    dispatcher.wake()
    for _ in range(50):
        if runner.calls:
            break
        await asyncio.sleep(0.02)
    await dispatcher.stop()

    assert runner.calls == ["t1"]


@pytest.mark.asyncio
async def test_bookkeeping_failure_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    """A failing bookkeeping write becomes one log line instead of an unretrieved task exception."""
    store = _BrokenStore()
    board = _board()
    await store.save_board(board)
    running = _ready("t1")
    running.status = TaskStatus.RUNNING
    await store.save_task(running)

    dispatcher = KanbanDispatcher(store, _RecordingRunner(), board)
    await dispatcher._execute_task("t1")

    assert "bookkeeping failed" in caplog.text


@pytest.mark.asyncio
async def test_skip_rescue_leaves_orphan_reclaim_to_the_caller() -> None:
    """With rescue_orphans=False the boot path does not query RUNNING tasks per board."""
    store = InMemoryKanbanStore()
    board = _board()
    await store.save_board(board)
    orphan = _ready("t1")
    orphan.status = TaskStatus.RUNNING
    await store.save_task(orphan)
    calls: list[str] = []
    original = store.list_running_tasks

    async def counting_list_running_tasks(board_id: str) -> list[KanbanTask]:
        calls.append(board_id)
        return await original(board_id)

    store.list_running_tasks = counting_list_running_tasks  # type: ignore[method-assign]
    dispatcher = KanbanDispatcher(store, _RecordingRunner(), board)
    await dispatcher.start(rescue_orphans=False)
    await dispatcher.stop()

    assert calls == []
    task = await store.get_task("t1")
    assert task is not None
    assert task.status == TaskStatus.RUNNING
