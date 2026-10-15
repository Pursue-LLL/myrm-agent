"""A dependent task builds its workspace only after its parents' merges have landed.

[INPUT]
- app.services.kanban.worktree_landing::register_landing, wait_parents_landed (POS: in-flight merges of completed tasks)
- app.services.kanban.worktree_ops::spawn_worktree_op (POS: off-request worktree work, registers the merge it runs)
- app.services.kanban.dispatcher_lifecycle::_make_task_completed_merge_hook (POS: dispatcher task_completed merge hook)
- app.services.kanban.move_orchestrator::move_task (POS: manual COMPLETED move that merges in the background)
- myrm_agent_harness KanbanDispatcher + InMemoryKanbanStore + a throwaway git repo (real git for the end-to-end cases)

[OUTPUT]
Pins that a child the dispatcher starts right after its parent completes still finds the parent's merged files, however
slow the merge is; that the same holds for a manual move and for a child without a branch; and that waiting never
reads the store when nothing is merging, never cancels a merge, and never holds a dependent back for good.

[POS]
tests/services/kanban/test_worktree_landing.py
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard, KanbanTask, TaskStatus

from app.services.kanban import worktree_landing
from app.services.kanban.dispatcher_lifecycle import _make_task_completed_merge_hook
from app.services.kanban.move_orchestrator import move_task
from app.services.kanban.task_runner.worktree import merge_task_worktree, resolve_workspace
from app.services.kanban.worktree_landing import register_landing, wait_parents_landed
from app.services.kanban.worktree_ops import spawn_worktree_op

BOARD_ID = "b1"
WAIT_SECONDS = 20
# A real merge on a large repository takes hundreds of milliseconds; this makes the race deterministic on a tiny one.
SLOW_MERGE_SECONDS = 0.3
SETTLE_ROUNDS = 20


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
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


class _WorktreeRunner:
    """The agent run is replaced by one file write; workspace resolution and merging are the production code."""

    def __init__(self, store: InMemoryKanbanStore) -> None:
        self._store = store
        self.seen_at_start: dict[str, set[str]] = {}

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        workspace = await resolve_workspace(self._store, task)
        assert workspace is not None
        self.seen_at_start[task.task_id] = {path.name for path in Path(workspace).iterdir()}
        (Path(workspace) / f"{task.task_id}.txt").write_text("output\n", encoding="utf-8")
        return True, "done"

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        await asyncio.sleep(SLOW_MERGE_SECONDS)
        return await merge_task_worktree(self._store, task)


async def _seed_chain(
    store: InMemoryKanbanStore, workspace: Path, parents: list[str], child: str, *, child_branch: str = "main"
) -> KanbanBoard:
    board = KanbanBoard(
        board_id=BOARD_ID,
        name="Board",
        settings=BoardSettings(max_concurrent_tasks=4, heartbeat_interval_seconds=1, zombie_timeout_seconds=60),
    )
    await store.save_board(board)
    for task_id in [*parents, child]:
        is_parent = task_id in parents
        await store.save_task(
            KanbanTask(
                task_id=task_id,
                board_id=BOARD_ID,
                title=task_id,
                status=TaskStatus.READY if is_parent else TaskStatus.BACKLOG,
                branch="main" if is_parent else child_branch,
                workspace_path=str(workspace),
            )
        )
    for parent in parents:
        await store.add_edge(parent, child)
    return board


async def _run_board(store: InMemoryKanbanStore, board: KanbanBoard, runner: _WorktreeRunner, finished: str) -> None:
    dispatcher = KanbanDispatcher(store, runner, board)
    dispatcher.on_event(_make_task_completed_merge_hook(runner, store))
    await dispatcher.start()
    try:

        async def until_done() -> None:
            while (task := await store.get_task(finished)) is None or task.status != TaskStatus.COMPLETED:
                await asyncio.sleep(0.02)

        await asyncio.wait_for(until_done(), timeout=WAIT_SECONDS)
        await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)
    finally:
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_child_started_by_the_dispatcher_sees_the_parent_merged_work(git_repo: Path) -> None:
    store = InMemoryKanbanStore()
    board = await _seed_chain(store, git_repo, ["parent01"], "child001")
    runner = _WorktreeRunner(store)

    await _run_board(store, board, runner, "child001")

    assert "parent01.txt" in runner.seen_at_start["child001"]
    assert (git_repo / "parent01.txt").exists()
    assert (git_repo / "child001.txt").exists()


@pytest.mark.asyncio
async def test_child_with_two_parents_sees_both_merged_works(git_repo: Path) -> None:
    store = InMemoryKanbanStore()
    board = await _seed_chain(store, git_repo, ["parent01", "parent02"], "child001")
    runner = _WorktreeRunner(store)

    await _run_board(store, board, runner, "child001")

    assert {"parent01.txt", "parent02.txt"} <= runner.seen_at_start["child001"]


@pytest.mark.asyncio
async def test_child_without_a_branch_does_not_start_inside_a_half_merged_checkout(git_repo: Path) -> None:
    # Without a branch the child works in the base directory itself, which the parent's merge is writing to.
    store = InMemoryKanbanStore()
    board = await _seed_chain(store, git_repo, ["parent01"], "child001", child_branch="")
    runner = _WorktreeRunner(store)

    await _run_board(store, board, runner, "child001")

    assert "parent01.txt" in runner.seen_at_start["child001"]


class _GatedMergeRunner:
    """A runner whose merge stays in flight until ``gate`` opens."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        await self.gate.wait()
        return True, []

    async def cleanup_worktree(self, task: KanbanTask) -> bool:
        return True


async def _settle() -> None:
    for _ in range(SETTLE_ROUNDS):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_child_of_a_manually_completed_task_waits_for_its_queued_merge(tmp_path: Path) -> None:
    store, runner = InMemoryKanbanStore(), _GatedMergeRunner()
    await _seed_chain(store, tmp_path, ["parent01"], "child001", child_branch="")
    dispatchers = {BOARD_ID: MagicMock(spec=KanbanDispatcher)}
    await move_task(store, dispatchers, runner, "parent01", TaskStatus.COMPLETED, wake_dispatcher=lambda _board_id: None)
    child = await store.get_task("child001")
    assert child is not None

    # Promoting the child by hand is allowed once the parent is COMPLETED, while its merge is still queued.
    resolving = asyncio.create_task(resolve_workspace(store, child))
    await _settle()
    assert not resolving.done()

    runner.gate.set()
    assert await asyncio.wait_for(resolving, timeout=WAIT_SECONDS) == str(tmp_path)
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)


class _NoReadStore(InMemoryKanbanStore):
    async def list_parents(self, task_id: str) -> list[str]:
        raise AssertionError("the store must not be read while no merge is in flight")


async def _child_of(store: InMemoryKanbanStore, *parents: str) -> KanbanTask:
    await store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    child = await store.save_task(KanbanTask(task_id="child001", board_id=BOARD_ID, title="child"))
    for parent in parents:
        await store.add_edge(parent, child.task_id)
    return child


def _start_merge(task_id: str) -> tuple[asyncio.Event, asyncio.Task[None]]:
    release = asyncio.Event()

    async def merge() -> None:
        await release.wait()

    merging = asyncio.get_running_loop().create_task(merge())
    register_landing(task_id, merging)
    return release, merging


@pytest.mark.asyncio
async def test_waiting_costs_nothing_while_no_merge_is_in_flight() -> None:
    store = _NoReadStore()
    child = await _child_of(store, "parent01")

    await asyncio.wait_for(wait_parents_landed(store, child), timeout=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_merge_of_an_unrelated_task_does_not_delay_the_child() -> None:
    store = InMemoryKanbanStore()
    child = await _child_of(store, "parent01")
    release, merging = _start_merge("other001")

    await asyncio.wait_for(wait_parents_landed(store, child), timeout=WAIT_SECONDS)

    assert not merging.done()
    release.set()
    await merging


@pytest.mark.asyncio
async def test_the_child_waits_until_every_merging_parent_has_landed() -> None:
    store = InMemoryKanbanStore()
    child = await _child_of(store, "parent01", "parent02")
    first_release, first = _start_merge("parent01")
    second_release, second = _start_merge("parent02")
    waiting = asyncio.create_task(wait_parents_landed(store, child))

    await _settle()
    assert not waiting.done()
    first_release.set()
    await first
    await _settle()
    assert not waiting.done()
    second_release.set()
    await second
    await asyncio.wait_for(waiting, timeout=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_finished_merge_is_forgotten() -> None:
    store = _NoReadStore()
    child = await _child_of(store, "parent01")
    release, merging = _start_merge("parent01")
    release.set()
    await merging
    await _settle()

    await asyncio.wait_for(wait_parents_landed(store, child), timeout=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_newer_merge_of_the_same_task_is_not_forgotten_when_the_older_one_finishes() -> None:
    store = InMemoryKanbanStore()
    child = await _child_of(store, "parent01")
    older_release, older = _start_merge("parent01")
    newer_release, newer = _start_merge("parent01")
    older_release.set()
    await older
    await _settle()

    waiting = asyncio.create_task(wait_parents_landed(store, child))
    await _settle()
    assert not waiting.done()
    newer_release.set()
    await newer
    await asyncio.wait_for(waiting, timeout=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_failed_merge_still_ends_the_wait() -> None:
    store = InMemoryKanbanStore()
    child = await _child_of(store, "parent01")
    started = asyncio.Event()

    async def explode() -> None:
        await started.wait()
        raise RuntimeError("git exploded")

    spawn_worktree_op(explode(), lands="parent01")
    waiting = asyncio.create_task(wait_parents_landed(store, child))
    await _settle()
    assert not waiting.done()
    started.set()

    await asyncio.wait_for(waiting, timeout=WAIT_SECONDS)
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_an_operation_spawned_without_a_landing_never_delays_a_child() -> None:
    store = _NoReadStore()
    child = await _child_of(store, "parent01")
    release = asyncio.Event()

    async def operation() -> None:
        await release.wait()

    spawn_worktree_op(operation())

    await asyncio.wait_for(wait_parents_landed(store, child), timeout=WAIT_SECONDS)
    release.set()
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_merge_that_never_ends_holds_the_child_back_only_for_the_limit_and_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worktree_landing, "_LANDING_WAIT_SECONDS", 0.05)
    store = InMemoryKanbanStore()
    child = await _child_of(store, "parent01")
    release, merging = _start_merge("parent01")

    await asyncio.wait_for(wait_parents_landed(store, child), timeout=WAIT_SECONDS)

    assert not merging.done()
    release.set()
    await merging
    assert not merging.cancelled()


@pytest.mark.asyncio
async def test_cancelling_the_waiting_child_does_not_cancel_the_merge() -> None:
    store = InMemoryKanbanStore()
    child = await _child_of(store, "parent01")
    release, merging = _start_merge("parent01")
    waiting = asyncio.create_task(wait_parents_landed(store, child))
    await _settle()

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert not merging.done()
    release.set()
    await merging
    assert not merging.cancelled()
