"""move_task hands a branch task's worktree merge/cleanup to a background task.

[INPUT]
- app.services.kanban.move_orchestrator::move_task (POS: kanban state transitions)
- app.services.kanban.worktree_ops::spawn_worktree_op (POS: off-request worktree work)
- InMemoryKanbanStore + a throwaway git repo (real git for the end-to-end cases)

[OUTPUT]
Pins that the request returns while git is still working, that dependents are released only after the
merge has landed, that nothing is lost when the merge fails, and that queued operations run only a few at a time.

[POS]
tests/services/kanban/test_move_task_worktree_ops.py
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskEventKind, TaskStatus

from app.services.kanban.move_orchestrator import _merge_then_release_dependents, move_task
from app.services.kanban.task_runner.worktree import cleanup_worktree, create_worktree, merge_task_worktree
from app.services.kanban.worktree_ops import _MAX_CONCURRENT_GIT_OPS, git_slot, spawn_worktree_op
from app.services.kanban.worktree_ops import merge_task_worktree as merge_task_worktree_op

BOARD_ID = "b1"
WAIT_SECONDS = 5


class _GatedRunner:
    """Records worktree operations and holds each one until ``gate`` opens, like a slow git call."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.calls: list[str] = []
        self.running = 0
        self.peak = 0

    async def _hold(self) -> None:
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await self.gate.wait()
        finally:
            self.running -= 1

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        await self._hold()
        self.calls.append(f"merge:{task.task_id}")
        return True, []

    async def cleanup_worktree(self, task: KanbanTask) -> bool:
        await self._hold()
        self.calls.append(f"cleanup:{task.task_id}")
        return True


class _SlowCleanupRunner(_GatedRunner):
    """Cleanups are held until the gate opens; merges finish at once."""

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        self.calls.append(f"merge:{task.task_id}")
        return True, []


class _BrokenRunner:
    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        raise RuntimeError("git exploded")

    async def cleanup_worktree(self, task: KanbanTask) -> bool:
        return True


class _GitRunner:
    """The two methods KanbanTaskRunner exposes, backed by the real worktree helpers."""

    def __init__(self, store: InMemoryKanbanStore) -> None:
        self._store = store

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        return await merge_task_worktree(self._store, task)

    async def cleanup_worktree(self, task: KanbanTask) -> bool:
        return await cleanup_worktree(self._store, task)


async def _seed(store: InMemoryKanbanStore, *, branch: str = "", workspace: str = "") -> None:
    """A READY parent and a BACKLOG child that waits for it."""
    await store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    for task_id, status in (("parent", TaskStatus.READY), ("child", TaskStatus.BACKLOG)):
        await store.save_task(
            KanbanTask(
                task_id=task_id,
                board_id=BOARD_ID,
                title=task_id,
                status=status,
                branch=branch if task_id == "parent" else "",
                workspace_path=workspace,
            )
        )
    await store.add_edge("parent", "child")


async def _seed_branch_tasks(store: InMemoryKanbanStore, count: int) -> list[str]:
    """``count`` independent READY tasks that each own a worktree branch."""
    await store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    task_ids = [f"t{i}" for i in range(count)]
    for task_id in task_ids:
        await store.save_task(
            KanbanTask(task_id=task_id, board_id=BOARD_ID, title=task_id, status=TaskStatus.READY, branch="main")
        )
    return task_ids


async def _move(
    store: InMemoryKanbanStore, runner: object, status: TaskStatus, wakes: list[str], task_id: str = "parent"
) -> KanbanTask:
    dispatchers = {BOARD_ID: MagicMock(spec=KanbanDispatcher)}
    # A request that still waits for git would hang forever on the gated runner; fail fast instead.
    moved = await asyncio.wait_for(
        move_task(store, dispatchers, runner, task_id, status, wake_dispatcher=wakes.append),
        timeout=WAIT_SECONDS,
    )
    assert moved is not None
    return moved


async def _until(condition: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout=WAIT_SECONDS)


async def _status_of(store: InMemoryKanbanStore, task_id: str) -> TaskStatus:
    task = await store.get_task(task_id)
    assert task is not None
    return task.status


@pytest.mark.asyncio
async def test_completed_move_returns_before_the_merge_and_releases_dependents_after_it() -> None:
    store, runner, wakes = InMemoryKanbanStore(), _GatedRunner(), []
    await _seed(store, branch="main")

    moved = await _move(store, runner, TaskStatus.COMPLETED, wakes)

    assert moved.status == TaskStatus.COMPLETED
    assert runner.calls == []
    # The child branches off the repository when it starts, so it must not run before the merge lands.
    assert await _status_of(store, "child") == TaskStatus.BACKLOG
    assert wakes == [BOARD_ID]

    runner.gate.set()
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)

    assert runner.calls == ["merge:parent"]
    assert await _status_of(store, "child") == TaskStatus.READY
    assert wakes == [BOARD_ID, BOARD_ID]


@pytest.mark.asyncio
async def test_dependents_are_released_and_the_failure_is_recorded_when_the_merge_raises() -> None:
    store, wakes = InMemoryKanbanStore(), []
    await _seed(store, branch="main")

    await _move(store, _BrokenRunner(), TaskStatus.COMPLETED, wakes)
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)

    assert await _status_of(store, "child") == TaskStatus.READY
    events = await store.list_events("parent")
    failure = next(event for event in events if event.kind == TaskEventKind.MERGE_CONFLICT)
    assert failure.payload is not None
    assert "git exploded" in str(failure.payload["message"])


@pytest.mark.asyncio
async def test_dependents_are_released_even_when_shutdown_cancels_the_merge() -> None:
    store, runner, wakes = InMemoryKanbanStore(), _GatedRunner(), []
    await _seed(store, branch="main")
    parent = await store.get_task("parent")
    assert parent is not None
    parent.status = TaskStatus.COMPLETED  # the state move_task has already saved when it schedules the merge
    await store.save_task(parent)
    dispatchers = {BOARD_ID: MagicMock(spec=KanbanDispatcher)}

    job = asyncio.create_task(_merge_then_release_dependents(store, dispatchers, runner, parent, wakes.append))
    await asyncio.sleep(0)
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job

    assert runner.calls == []
    assert await _status_of(store, "child") == TaskStatus.READY
    assert wakes == [BOARD_ID]
    # The merge was running, and its git process may still finish after the cancellation, so nothing is claimed.
    assert all(event.kind != TaskEventKind.MERGE_CONFLICT for event in await store.list_events("parent"))


@pytest.mark.asyncio
async def test_archived_move_returns_before_the_cleanup_and_still_releases_dependents_at_once() -> None:
    store, runner, wakes = InMemoryKanbanStore(), _GatedRunner(), []
    await _seed(store, branch="main")

    moved = await _move(store, runner, TaskStatus.ARCHIVED, wakes)

    assert moved.status == TaskStatus.ARCHIVED
    assert runner.calls == []
    assert await _status_of(store, "child") == TaskStatus.READY

    runner.gate.set()
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)

    assert runner.calls == ["cleanup:parent"]


@pytest.mark.asyncio
async def test_task_without_a_branch_releases_dependents_inline_and_never_touches_the_runner() -> None:
    store, runner, wakes = InMemoryKanbanStore(), _GatedRunner(), []
    await _seed(store)
    runner.gate.set()

    await _move(store, runner, TaskStatus.COMPLETED, wakes)

    assert await _status_of(store, "child") == TaskStatus.READY
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)
    assert runner.calls == []
    assert wakes == [BOARD_ID]


@pytest.mark.asyncio
async def test_moved_tasks_run_a_few_worktree_operations_at_a_time_and_all_finish() -> None:
    store, runner, wakes = InMemoryKanbanStore(), _GatedRunner(), []
    task_ids = await _seed_branch_tasks(store, 6)
    for task_id in task_ids[:3]:
        await _move(store, runner, TaskStatus.ARCHIVED, wakes, task_id)
    for task_id in task_ids[3:]:
        await _move(store, runner, TaskStatus.COMPLETED, wakes, task_id)

    await _until(lambda: runner.running == _MAX_CONCURRENT_GIT_OPS)
    for _ in range(20):  # a third would have started by now if nothing held it back
        await asyncio.sleep(0)
    assert runner.running == _MAX_CONCURRENT_GIT_OPS

    runner.gate.set()
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)

    assert len(runner.calls) == len(task_ids)
    assert runner.peak == _MAX_CONCURRENT_GIT_OPS


@pytest.mark.asyncio
async def test_a_merge_the_dispatcher_starts_is_not_queued_behind_background_cleanups() -> None:
    # The dispatcher promotes a finished task's dependents right after it schedules the merge, so that merge must not
    # wait for a bulk archive's queue.
    store, runner, wakes = InMemoryKanbanStore(), _SlowCleanupRunner(), []
    task_ids = await _seed_branch_tasks(store, _MAX_CONCURRENT_GIT_OPS + 2)
    for task_id in task_ids[:-1]:
        await _move(store, runner, TaskStatus.ARCHIVED, wakes, task_id)
    await _until(lambda: runner.running == _MAX_CONCURRENT_GIT_OPS)
    last = await store.get_task(task_ids[-1])
    assert last is not None

    merged = await asyncio.wait_for(merge_task_worktree_op(runner, last), timeout=WAIT_SECONDS)

    assert merged == (True, [])
    assert runner.calls == [f"merge:{last.task_id}"]
    runner.gate.set()
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_merge_cancelled_before_it_starts_is_recorded_and_still_releases_dependents() -> None:
    store, runner, wakes = InMemoryKanbanStore(), _GatedRunner(), []
    await _seed(store, branch="main")
    parent = await store.get_task("parent")
    assert parent is not None
    parent.status = TaskStatus.COMPLETED
    await store.save_task(parent)
    dispatchers = {BOARD_ID: MagicMock(spec=KanbanDispatcher)}
    slots = git_slot()
    for _ in range(_MAX_CONCURRENT_GIT_OPS):
        await slots.acquire()

    try:
        job = asyncio.create_task(_merge_then_release_dependents(store, dispatchers, runner, parent, wakes.append))
        await asyncio.sleep(0)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
    finally:
        for _ in range(_MAX_CONCURRENT_GIT_OPS):
            slots.release()

    assert runner.calls == []
    events = await store.list_events("parent")
    skipped = next(event for event in events if event.kind == TaskEventKind.MERGE_CONFLICT)
    assert skipped.payload is not None
    assert "did not run" in str(skipped.payload["message"])
    assert await _status_of(store, "child") == TaskStatus.READY


@pytest.mark.asyncio
async def test_spawned_operation_failure_is_logged_and_does_not_escape(caplog: pytest.LogCaptureFixture) -> None:
    async def explode() -> None:
        raise RuntimeError("disk gone")

    with caplog.at_level(logging.ERROR, logger="app.services.kanban.worktree_ops"):
        spawn_worktree_op(explode())
        await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)

    assert "Background worktree operation failed" in caplog.text
    assert "disk gone" in caplog.text


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, timeout=30)
    return done.stdout


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


@pytest.mark.asyncio
async def test_completed_move_lands_the_task_commits_and_removes_the_worktree(git_repo: Path) -> None:
    store, wakes = InMemoryKanbanStore(), []
    await _seed(store, branch="main", workspace=str(git_repo))
    worktree = await create_worktree(str(git_repo), "main", "parent")
    assert isinstance(worktree, str)
    (Path(worktree) / "feature.txt").write_text("done\n", encoding="utf-8")
    _git(Path(worktree), "add", "-A")
    _git(Path(worktree), "commit", "-q", "-m", "parent task commit")

    await _move(store, _GitRunner(store), TaskStatus.COMPLETED, wakes)
    await wait_all_background_tasks(timeout_seconds=30)

    assert "parent task commit" in _git(git_repo, "log", "--format=%s", "main")
    assert (git_repo / "feature.txt").read_text(encoding="utf-8") == "done\n"
    assert not Path(worktree).exists()
    assert await _status_of(store, "child") == TaskStatus.READY


@pytest.mark.asyncio
async def test_archived_move_removes_the_clean_worktree_in_the_background(git_repo: Path) -> None:
    store, wakes = InMemoryKanbanStore(), []
    await _seed(store, branch="main", workspace=str(git_repo))
    worktree = await create_worktree(str(git_repo), "main", "parent")
    assert isinstance(worktree, str)

    await _move(store, _GitRunner(store), TaskStatus.ARCHIVED, wakes)
    await wait_all_background_tasks(timeout_seconds=30)

    assert not Path(worktree).exists()
