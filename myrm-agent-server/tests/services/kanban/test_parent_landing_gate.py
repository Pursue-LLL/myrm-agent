"""A dependent task is held while a completed parent's code never landed on its branch.

[INPUT]
- app.services.kanban.task_runner.worktree.landing_gate::hold_for_unlanded_parents (POS: run-entry gate on parents' failed merges)
- app.services.kanban.task_runner.runner::KanbanTaskRunner (POS: the production run entry the gate sits in)
- app.services.kanban.dispatcher_lifecycle::_make_task_completed_merge_hook (POS: the merge the dispatcher starts on completion)
- myrm_agent_harness InMemoryKanbanStore + a throwaway git repo (real merges and real MERGE_CONFLICT events)

[OUTPUT]
Pins that a dependent whose parent's merge failed does not start its agent (nothing is built for it either) until the
user has acknowledged that failure; that an acknowledgement covers only the failures it saw; and that a parent which
landed, was completed again, lives in another repository, or is not completed never holds a dependent back.

[POS]
tests/services/kanban/test_parent_landing_gate.py
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanBoard,
    KanbanTask,
    TaskEvent,
    TaskEventKind,
    TaskExecutionResult,
    TaskStatus,
)

from app.services.kanban.dispatcher_lifecycle import _make_task_completed_merge_hook
from app.services.kanban.task_runner import KanbanTaskRunner
from app.services.kanban.task_runner.worktree import merge_task_worktree, resolve_workspace
from app.services.kanban.task_runner.worktree.landing_gate import (
    ACKNOWLEDGED_MERGE_FAILURE_KEY,
    PARENT_MERGE_FAILED_REASON,
    hold_for_unlanded_parents,
)

BOARD_ID = "b1"
WAIT_SECONDS = 20
RUNNER_MODULE = "app.services.kanban.task_runner.runner"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, timeout=30)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "shared.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


class _MergeRunner:
    """Merges with the production code; ``delay`` keeps the merge in flight for a while."""

    def __init__(self, store: InMemoryKanbanStore, delay: float = 0.0) -> None:
        self._store = store
        self._delay = delay

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        await asyncio.sleep(self._delay)
        return await merge_task_worktree(self._store, task)


@pytest.fixture
async def store() -> InMemoryKanbanStore:
    board_store = InMemoryKanbanStore()
    await board_store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    return board_store


async def _parent(store: InMemoryKanbanStore, repo: Path, task_id: str) -> KanbanTask:
    parent = await store.save_task(
        KanbanTask(task_id=task_id, board_id=BOARD_ID, title=task_id, branch="main", workspace_path=str(repo))
    )
    assert await resolve_workspace(store, parent) is not None
    return parent


def _write(path: Path, name: str, text: str) -> None:
    (path / name).write_text(text, encoding="utf-8")


async def _complete(
    store: InMemoryKanbanStore, runner: _MergeRunner, task: KanbanTask, marker: TaskEventKind = TaskEventKind.COMPLETED
) -> None:
    """What the dispatcher does when a task finishes: record it, then start the merge in the background."""
    task.status = TaskStatus.COMPLETED
    await store.save_task(task)
    await store.append_event(task.task_id, marker)
    _make_task_completed_merge_hook(runner, store)("task_completed", task)


async def _settle() -> None:
    await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)


async def _fail_to_land(
    store: InMemoryKanbanStore,
    runner: _MergeRunner,
    repo: Path,
    task_id: str,
    marker: TaskEventKind = TaskEventKind.COMPLETED,
) -> KanbanTask:
    """A parent whose merge conflicts with an edit another task made to the same file on the branch."""
    parent = await _parent(store, repo, task_id)
    workdir = Path(await resolve_workspace(store, parent) or "")
    _write(workdir, "shared.txt", f"{task_id} edit\n")
    _write(repo, "shared.txt", f"main edit before {task_id}\n")
    _git(repo, "commit", "-qam", f"main edit before {task_id}")
    await _complete(store, runner, parent, marker)
    return parent


async def _land(store: InMemoryKanbanStore, runner: _MergeRunner, repo: Path, task_id: str) -> KanbanTask:
    parent = await _parent(store, repo, task_id)
    _write(Path(await resolve_workspace(store, parent) or ""), f"{task_id}.txt", "output\n")
    await _complete(store, runner, parent)
    return parent


async def _child(
    store: InMemoryKanbanStore, repo: Path | str, *parents: KanbanTask, metadata: dict[str, object] | None = None
) -> KanbanTask:
    child = await store.save_task(
        KanbanTask(
            task_id="child001",
            board_id=BOARD_ID,
            title="child",
            branch="main",
            workspace_path=str(repo),
            metadata=metadata or {},
        )
    )
    for parent in parents:
        await store.add_edge(parent.task_id, child.task_id)
    return child


async def _failure_event_id(store: InMemoryKanbanStore, task_id: str) -> int:
    failures = [event for event in await store.list_events(task_id) if event.kind == TaskEventKind.MERGE_CONFLICT]
    return failures[-1].event_id


@pytest.mark.asyncio
async def test_a_dependent_is_held_while_its_parent_failed_to_land(git_repo: Path, store: InMemoryKanbanStore) -> None:
    runner = _MergeRunner(store)
    parent = await _fail_to_land(store, runner, git_repo, "parent01")
    await _settle()
    child = await _child(store, git_repo, parent)

    held = await hold_for_unlanded_parents(store, child)

    assert held is not None
    assert held.is_blocked
    assert held.block_kind == BlockKind.HUMAN
    assert held.blocked_reason == PARENT_MERGE_FAILED_REASON
    assert held.metadata_patch == {ACKNOWLEDGED_MERGE_FAILURE_KEY: await _failure_event_id(store, "parent01")}


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", [TaskEventKind.COMPLETED, TaskEventKind.APPROVED])
async def test_either_way_of_completing_a_task_counts(git_repo: Path, store: InMemoryKanbanStore, marker: TaskEventKind) -> None:
    runner = _MergeRunner(store)
    parent = await _fail_to_land(store, runner, git_repo, "parent01", marker)
    await _settle()

    assert await hold_for_unlanded_parents(store, await _child(store, git_repo, parent)) is not None


@pytest.mark.asyncio
async def test_the_gate_waits_for_the_merge_still_in_flight_before_it_judges(git_repo: Path, store: InMemoryKanbanStore) -> None:
    runner = _MergeRunner(store, delay=0.3)
    parent = await _fail_to_land(store, runner, git_repo, "parent01")
    child = await _child(store, git_repo, parent)

    held = await asyncio.wait_for(hold_for_unlanded_parents(store, child), timeout=WAIT_SECONDS)

    assert held is not None
    await _settle()


@pytest.mark.asyncio
async def test_a_parent_that_landed_does_not_hold_the_dependent(git_repo: Path, store: InMemoryKanbanStore) -> None:
    runner = _MergeRunner(store)
    parent = await _land(store, runner, git_repo, "parent01")
    await _settle()

    assert await hold_for_unlanded_parents(store, await _child(store, git_repo, parent)) is None
    assert (git_repo / "parent01.txt").exists()


@pytest.mark.asyncio
async def test_a_task_without_parents_is_never_held(git_repo: Path, store: InMemoryKanbanStore) -> None:
    assert await hold_for_unlanded_parents(store, await _child(store, git_repo)) is None


@pytest.mark.asyncio
async def test_one_failed_parent_among_landed_ones_holds_the_dependent(git_repo: Path, store: InMemoryKanbanStore) -> None:
    runner = _MergeRunner(store)
    landed = await _land(store, runner, git_repo, "parent01")
    await _settle()
    failed = await _fail_to_land(store, runner, git_repo, "parent02")
    await _settle()

    assert await hold_for_unlanded_parents(store, await _child(store, git_repo, landed, failed)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", [TaskEventKind.COMPLETED, TaskEventKind.APPROVED])
async def test_completing_the_parent_again_clears_its_earlier_failure(
    git_repo: Path, store: InMemoryKanbanStore, marker: TaskEventKind
) -> None:
    runner = _MergeRunner(store)
    parent = await _fail_to_land(store, runner, git_repo, "parent01")
    await _settle()
    await store.append_event("parent01", marker)

    assert await hold_for_unlanded_parents(store, await _child(store, git_repo, parent)) is None


@pytest.mark.asyncio
async def test_a_failure_the_user_has_acknowledged_does_not_hold_the_dependent_again(
    git_repo: Path, store: InMemoryKanbanStore
) -> None:
    runner = _MergeRunner(store)
    parent = await _fail_to_land(store, runner, git_repo, "parent01")
    await _settle()
    seen = await _failure_event_id(store, "parent01")
    child = await _child(store, git_repo, parent, metadata={ACKNOWLEDGED_MERGE_FAILURE_KEY: seen})

    assert await hold_for_unlanded_parents(store, child) is None


@pytest.mark.asyncio
async def test_a_newer_failure_holds_the_dependent_even_after_an_acknowledgement(
    git_repo: Path, store: InMemoryKanbanStore
) -> None:
    runner = _MergeRunner(store)
    first = await _fail_to_land(store, runner, git_repo, "parent01")
    await _settle()
    seen = await _failure_event_id(store, "parent01")
    second = await _fail_to_land(store, runner, git_repo, "parent02")
    await _settle()
    child = await _child(store, git_repo, first, second, metadata={ACKNOWLEDGED_MERGE_FAILURE_KEY: seen})

    held = await hold_for_unlanded_parents(store, child)

    assert held is not None
    assert held.metadata_patch == {ACKNOWLEDGED_MERGE_FAILURE_KEY: await _failure_event_id(store, "parent02")}


@pytest.mark.asyncio
async def test_a_parent_in_another_repository_does_not_hold_the_dependent(
    git_repo: Path, store: InMemoryKanbanStore, tmp_path: Path
) -> None:
    runner = _MergeRunner(store)
    parent = await _fail_to_land(store, runner, git_repo, "parent01")
    await _settle()
    other = tmp_path / "other"
    other.mkdir()

    assert await hold_for_unlanded_parents(store, await _child(store, other, parent)) is None


@pytest.mark.asyncio
async def test_a_parent_that_is_not_completed_does_not_hold_the_dependent(git_repo: Path, store: InMemoryKanbanStore) -> None:
    runner = _MergeRunner(store)
    parent = await _fail_to_land(store, runner, git_repo, "parent01")
    await _settle()
    parent.status = TaskStatus.READY
    await store.save_task(parent)

    assert await hold_for_unlanded_parents(store, await _child(store, git_repo, parent)) is None


class _NoEventReadStore(InMemoryKanbanStore):
    async def list_events(self, task_id: str, *, since_id: int | None = None) -> list[TaskEvent]:
        raise AssertionError("a parent without a branch never merges, so its events must not be read")


@pytest.mark.asyncio
async def test_a_parent_without_a_branch_is_judged_without_reading_its_events(git_repo: Path) -> None:
    store = _NoEventReadStore()
    await store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    parent = await store.save_task(
        KanbanTask(
            task_id="parent01",
            board_id=BOARD_ID,
            title="parent",
            workspace_path=str(git_repo),
            status=TaskStatus.COMPLETED,
        )
    )

    assert await hold_for_unlanded_parents(store, await _child(store, git_repo, parent)) is None


class _RunSurface:
    """The pieces of ``KanbanTaskRunner.run`` around the agent, replaced so only the run entry is exercised."""

    def __init__(self, runner: KanbanTaskRunner) -> None:
        self.build_context = AsyncMock(return_value="context")
        self.execute_agent = AsyncMock(return_value=(False, "the agent ran"))
        self._patches = [
            patch(f"{RUNNER_MODULE}.build_task_context", self.build_context),
            patch(f"{RUNNER_MODULE}.resolve_agent_profile", AsyncMock(return_value=None)),
            patch(f"{RUNNER_MODULE}.build_multimodal_query", AsyncMock(return_value="query")),
            patch.object(runner, "_execute_agent", self.execute_agent),
        ]

    def __enter__(self) -> _RunSurface:
        for active in self._patches:
            active.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        for active in self._patches:
            active.stop()


@pytest.mark.asyncio
async def test_the_runner_builds_nothing_and_starts_no_agent_for_a_held_dependent(
    git_repo: Path, store: InMemoryKanbanStore
) -> None:
    parent = await _fail_to_land(store, _MergeRunner(store), git_repo, "parent01")
    await _settle()
    child = await _child(store, git_repo, parent)
    runner = KanbanTaskRunner(store)

    with _RunSurface(runner) as surface:
        outcome = await runner.run(child)

    assert isinstance(outcome, TaskExecutionResult)
    assert outcome.is_blocked
    assert outcome.blocked_reason == PARENT_MERGE_FAILED_REASON
    surface.build_context.assert_not_awaited()
    surface.execute_agent.assert_not_awaited()
    assert not Path(git_repo, ".worktrees", "main-child001").exists()


@pytest.mark.asyncio
async def test_the_runner_starts_the_agent_once_the_failure_is_acknowledged(git_repo: Path, store: InMemoryKanbanStore) -> None:
    parent = await _fail_to_land(store, _MergeRunner(store), git_repo, "parent01")
    await _settle()
    seen = await _failure_event_id(store, "parent01")
    child = await _child(store, git_repo, parent, metadata={ACKNOWLEDGED_MERGE_FAILURE_KEY: seen})
    runner = KanbanTaskRunner(store)

    with _RunSurface(runner) as surface:
        outcome = await runner.run(child)

    assert outcome == (False, "the agent ran")
    surface.execute_agent.assert_awaited_once()
