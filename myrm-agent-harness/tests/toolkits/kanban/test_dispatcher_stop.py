"""Stopping a KanbanDispatcher: the loops end at an iteration boundary instead of being cancelled in a store call.

Cancelling a loop while it is inside a database call aborts the call, and the teardown of that connection can wait
forever, which would block the stop (and the process shutdown behind it). The loops are therefore asked to leave;
cancellation is only the bounded fallback.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from myrm_agent_harness.toolkits.kanban import dispatcher_dispatch
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

_WAIT = 1.0


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        self.calls.append(task.task_id)
        return True, "ok"


class _BlockedStore(InMemoryKanbanStore):
    """Store whose ``list_running_tasks`` stays inside the call until released, like a database call in flight."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.interrupted = 0

    async def list_running_tasks(self, board_id: str) -> list[KanbanTask]:
        self.entered.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.interrupted += 1
                raise
        return await super().list_running_tasks(board_id)


class _DeafStore(_BlockedStore):
    """Store whose call survives cancellation, like a teardown that never completes."""

    async def list_running_tasks(self, board_id: str) -> list[KanbanTask]:
        self.entered.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.interrupted += 1
        return []


class _BlockedReadyStore(InMemoryKanbanStore):
    """Store whose ``list_ready_tasks`` stays inside the call until released."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def list_ready_tasks(self, board_id: str) -> list[KanbanTask]:
        self.entered.set()
        await self.release.wait()
        return await super().list_ready_tasks(board_id)


def _board() -> KanbanBoard:
    return KanbanBoard(
        board_id="b1",
        name="Board",
        settings=BoardSettings(max_concurrent_tasks=3, heartbeat_interval_seconds=60, zombie_timeout_seconds=600),
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
async def test_stop_returns_at_once_while_the_loops_sleep() -> None:
    d = KanbanDispatcher(InMemoryKanbanStore(), _RecordingRunner(), _board())
    await d.start(rescue_orphans=False)
    await asyncio.sleep(0.05)

    # Both loops sit in minute-long sleeps; stopping must not wait them out.
    await asyncio.wait_for(d.stop(), timeout=_WAIT)

    assert not d.is_running


@pytest.mark.asyncio
async def test_stop_lets_a_store_call_in_flight_finish() -> None:
    store = _BlockedStore()
    d = KanbanDispatcher(store, _RecordingRunner(), _board())
    await d.start(rescue_orphans=False)
    await asyncio.wait_for(store.entered.wait(), timeout=_WAIT)

    stopping = asyncio.create_task(d.stop())
    await asyncio.sleep(0.05)
    assert not stopping.done(), "stop returned while a loop was still inside a store call"
    assert store.interrupted == 0, "the in-flight store call was cancelled"

    store.release.set()
    await asyncio.wait_for(stopping, timeout=_WAIT)

    assert store.interrupted == 0
    assert not d.is_running


@pytest.mark.asyncio
async def test_stop_claims_no_further_task_once_requested() -> None:
    store = _BlockedReadyStore()
    await store.save_board(_board())
    await store.save_task(_ready("t1"))
    await store.save_task(_ready("t2"))
    runner = _RecordingRunner()
    d = KanbanDispatcher(store, runner, _board())
    await d.start(rescue_orphans=False)
    await asyncio.wait_for(store.entered.wait(), timeout=_WAIT)

    stopping = asyncio.create_task(d.stop())
    await asyncio.sleep(0.05)
    store.release.set()
    await asyncio.wait_for(stopping, timeout=_WAIT)

    assert runner.calls == []
    for task_id in ("t1", "t2"):
        task = await store.get_task(task_id)
        assert task is not None and task.status == TaskStatus.READY


@pytest.mark.asyncio
async def test_stop_cancels_a_loop_that_does_not_leave_in_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatcher_dispatch, "_LOOP_EXIT_GRACE_SECONDS", 0.05)
    store = _BlockedStore()
    d = KanbanDispatcher(store, _RecordingRunner(), _board())
    await d.start(rescue_orphans=False)
    await asyncio.wait_for(store.entered.wait(), timeout=_WAIT)

    await asyncio.wait_for(d.stop(), timeout=_WAIT)

    assert store.interrupted == 1
    assert not d.is_running


@pytest.mark.asyncio
async def test_stop_abandons_a_loop_that_ignores_cancellation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(dispatcher_dispatch, "_LOOP_EXIT_GRACE_SECONDS", 0.05)
    store = _DeafStore()
    d = KanbanDispatcher(store, _RecordingRunner(), _board())
    await d.start(rescue_orphans=False)
    await asyncio.wait_for(store.entered.wait(), timeout=_WAIT)
    stuck_loop = d._dispatch_task
    assert stuck_loop is not None

    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(d.stop(), timeout=_WAIT)

    assert "did not end after cancellation" in caplog.text
    assert not stuck_loop.done()
    store.release.set()
    await asyncio.wait_for(stuck_loop, timeout=_WAIT)


@pytest.mark.asyncio
async def test_a_stopped_dispatcher_starts_again_with_sleeping_loops() -> None:
    d = KanbanDispatcher(InMemoryKanbanStore(), _RecordingRunner(), _board())
    await d.start(rescue_orphans=False)
    await d.stop()

    await d.start(rescue_orphans=False)
    await asyncio.sleep(0.1)
    zombie_loop = d._zombie_task

    # The previous stop must not leave the loops' sleeps pre-expired, or they would spin or exit at once.
    assert zombie_loop is not None and not zombie_loop.done()
    await asyncio.wait_for(d.stop(), timeout=_WAIT)
    assert zombie_loop.done()
