"""The dispatcher holds a dependent whose parent's merge failed, and releases it once the user continues.

[INPUT]
- myrm_agent_harness KanbanDispatcher + InMemoryKanbanStore + a throwaway git repo (real merges, real MERGE_CONFLICT events)
- app.services.kanban.task_runner::KanbanTaskRunner (POS: the production run entry holding the dependent)
- app.services.kanban.move_orchestrator::move_task (POS: the manual BLOCKED to READY move a user makes to continue)

[OUTPUT]
Pins the whole path of one dependent: the parent's merge conflicts, the dispatcher starts the dependent, the run entry
blocks it for the user without a model call or a failure count, moving it back to READY runs it, and the same failure
never blocks it twice.

[POS]
tests/services/kanban/test_parent_landing_gate_dispatch.py
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    KANBAN_COMPLETION_INTENT_KEY,
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskEventKind,
    TaskExecutionResult,
    TaskRunOutcome,
    TaskStatus,
)

from app.services.kanban.dispatcher_lifecycle import _make_task_completed_merge_hook
from app.services.kanban.move_orchestrator import move_task
from app.services.kanban.task_runner import KanbanTaskRunner
from app.services.kanban.task_runner.worktree import merge_task_worktree, resolve_workspace
from app.services.kanban.task_runner.worktree.landing_gate import (
    ACKNOWLEDGED_MERGE_FAILURE_KEY,
    PARENT_MERGE_FAILED_REASON,
)

BOARD_ID = "b1"
PARENT_ID = "parent01"
CHILD_ID = "child001"
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


class _Runner:
    """The parent edits a file that main edits too, so its merge conflicts; the dependent goes through the production run entry."""

    def __init__(self, store: InMemoryKanbanStore, repo: Path) -> None:
        self._store = store
        self._repo = repo
        self.production = KanbanTaskRunner(store)

    async def run(self, task: KanbanTask) -> tuple[bool, str] | TaskExecutionResult:
        if task.task_id != PARENT_ID:
            return await self.production.run(task)
        workspace = Path(await resolve_workspace(self._store, task) or "")
        (workspace / "shared.txt").write_text("parent edit\n", encoding="utf-8")
        (self._repo / "shared.txt").write_text("main edit\n", encoding="utf-8")
        _git(self._repo, "commit", "-qam", "main edit")
        return True, "done"

    async def merge_task_worktree(self, task: KanbanTask) -> tuple[bool, list[str]]:
        return await merge_task_worktree(self._store, task)


async def _seed(store: InMemoryKanbanStore, repo: Path) -> KanbanBoard:
    board = KanbanBoard(
        board_id=BOARD_ID,
        name="Board",
        settings=BoardSettings(max_concurrent_tasks=4, heartbeat_interval_seconds=1, zombie_timeout_seconds=60),
    )
    await store.save_board(board)
    for task_id, status in ((PARENT_ID, TaskStatus.READY), (CHILD_ID, TaskStatus.BACKLOG)):
        await store.save_task(
            KanbanTask(task_id=task_id, board_id=BOARD_ID, title=task_id, status=status, branch="main", workspace_path=str(repo))
        )
    await store.add_edge(PARENT_ID, CHILD_ID)
    return board


async def _until(store: InMemoryKanbanStore, task_id: str, done: Callable[[KanbanTask], bool]) -> KanbanTask:
    async def poll() -> KanbanTask:
        while (task := await store.get_task(task_id)) is None or not done(task):
            await asyncio.sleep(0.02)
        return task

    return await asyncio.wait_for(poll(), timeout=WAIT_SECONDS)


async def _within_dispatcher(
    store: InMemoryKanbanStore, repo: Path, scenario: Callable[[KanbanDispatcher, _Runner, AsyncMock], Awaitable[None]]
) -> None:
    board = await _seed(store, repo)
    runner = _Runner(store, repo)
    dispatcher = KanbanDispatcher(store, runner, board)
    dispatcher.on_event(_make_task_completed_merge_hook(runner, store))

    async def finish_through_kanban_complete(task: KanbanTask, *_args: object, **_kwargs: object) -> tuple[bool, str]:
        """What a worker that calls ``kanban_complete`` leaves behind: the completion intent and its summary."""
        fresh = await store.get_task(task.task_id)
        assert fresh is not None
        fresh.metadata = {**fresh.metadata, KANBAN_COMPLETION_INTENT_KEY: True}
        fresh.result = "done"
        await store.save_task(fresh)
        return True, "done"

    execute_agent = AsyncMock(side_effect=finish_through_kanban_complete)
    with (
        patch(f"{RUNNER_MODULE}.build_task_context", AsyncMock(return_value="context")),
        patch(f"{RUNNER_MODULE}.resolve_agent_profile", AsyncMock(return_value=None)),
        patch(f"{RUNNER_MODULE}.build_multimodal_query", AsyncMock(return_value="query")),
        patch.object(runner.production, "_execute_agent", execute_agent),
    ):
        await dispatcher.start()
        try:
            await scenario(dispatcher, runner, execute_agent)
        finally:
            await dispatcher.stop()
            await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_a_dependent_is_blocked_for_the_user_then_runs_once_the_user_continues(git_repo: Path) -> None:
    store = InMemoryKanbanStore()

    async def scenario(dispatcher: KanbanDispatcher, runner: _Runner, execute_agent: AsyncMock) -> None:
        held = await _until(store, CHILD_ID, lambda task: task.status == TaskStatus.BLOCKED)
        failure_ids = [
            event.event_id for event in await store.list_events(PARENT_ID) if event.kind == TaskEventKind.MERGE_CONFLICT
        ]
        assert len(failure_ids) == 1
        assert (held.block_kind, held.blocked_reason) == (BlockKind.HUMAN, PARENT_MERGE_FAILED_REASON)
        assert held.metadata[ACKNOWLEDGED_MERGE_FAILURE_KEY] == failure_ids[0]
        assert held.consecutive_failures == 0
        execute_agent.assert_not_awaited()
        assert [run.outcome for run in await store.list_runs(CHILD_ID)] == [TaskRunOutcome.BLOCKED]

        await move_task(
            store, {BOARD_ID: dispatcher}, runner, CHILD_ID, TaskStatus.READY, wake_dispatcher=lambda _board_id: dispatcher.wake()
        )
        finished = await _until(store, CHILD_ID, lambda task: task.status == TaskStatus.COMPLETED)

        execute_agent.assert_awaited_once()
        assert finished.metadata[ACKNOWLEDGED_MERGE_FAILURE_KEY] == failure_ids[0]
        blocks = [event for event in await store.list_events(CHILD_ID) if event.kind == TaskEventKind.BLOCKED]
        assert len(blocks) == 1

    await _within_dispatcher(store, git_repo, scenario)
