"""Tests for resolve_workspace event semantics and fallback behavior."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskEventKind

from app.core.utils.git_worktree import WorktreeCreateError, WorktreeErrorReason
from app.services.kanban.task_runner.worktree import resolve_workspace, worktree_dir


async def _seed_task(store: InMemoryKanbanStore, *, task_id: str, base: str, branch: str | None) -> KanbanTask:
    await store.save_board(KanbanBoard(board_id="b1", name="Board"))
    task = KanbanTask(
        task_id=task_id,
        board_id="b1",
        title="Worktree task",
        workspace_path=base,
        branch=branch,
    )
    return await store.save_task(task)


async def _branch_events(store: InMemoryKanbanStore, task_id: str) -> list:
    return [e for e in await store.list_events(task_id) if e.kind == TaskEventKind.BRANCH_SWITCHED]


@pytest.mark.asyncio
async def test_attach_caller_reuse_does_not_duplicate_branch_event(
    tmp_path: Path,
) -> None:
    """A worktree that already exists must not emit BRANCH_SWITCHED again.

    This covers the attach-handler path: resolve_workspace is called on every
    kanban_attach while the task is RUNNING, so a second call (worktree already
    created by the runner) must stay event-silent instead of spamming the
    task timeline with duplicate 'Branch Switched' entries.
    """
    base = tmp_path / "repo"
    base.mkdir()
    worktree = tmp_path / "wt_feat"
    worktree.mkdir()

    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="t_wt", base=str(base), branch="feat")
    wt_path = worktree_dir(str(base), "feat", task.task_id)
    # Pre-create the worktree dir so the resolver treats it as already existing.
    Path(wt_path).mkdir(parents=True)

    with patch(
        "app.services.kanban.task_runner.worktree.lifecycle.create_worktree",
        new_callable=AsyncMock,
        return_value=wt_path,
    ):
        resolved = await resolve_workspace(store, task)
    assert resolved == wt_path
    assert await _branch_events(store, task.task_id) == []


@pytest.mark.asyncio
async def test_first_resolve_emits_branch_event_once(tmp_path: Path) -> None:
    """A worktree created on demand emits exactly one BRANCH_SWITCHED event."""
    base = tmp_path / "repo"
    base.mkdir()

    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="t_new", base=str(base), branch="feat")
    wt_path = worktree_dir(str(base), "feat", task.task_id)

    with patch(
        "app.services.kanban.task_runner.worktree.lifecycle.create_worktree",
        new_callable=AsyncMock,
        return_value=wt_path,
    ):
        resolved = await resolve_workspace(store, task)
    assert resolved == wt_path
    assert len(await _branch_events(store, task.task_id)) == 1


@pytest.mark.asyncio
async def test_no_branch_returns_base_dir_without_event(tmp_path: Path) -> None:
    """Tasks without branch isolation resolve to the base dir and emit nothing."""
    base = tmp_path / "repo"
    base.mkdir()

    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="t_plain", base=str(base), branch=None)

    resolved = await resolve_workspace(store, task)
    assert resolved == str(base)
    assert await _branch_events(store, task.task_id) == []


@pytest.mark.asyncio
async def test_worktree_creation_failure_falls_back_without_event(
    tmp_path: Path,
) -> None:
    """Worktree creation failure falls back to the base dir and emits nothing."""
    base = tmp_path / "repo"
    base.mkdir()

    store = InMemoryKanbanStore()
    task = await _seed_task(store, task_id="t_fail", base=str(base), branch="feat")

    error = WorktreeCreateError(reason=WorktreeErrorReason.ERROR, message="boom")
    with patch(
        "app.services.kanban.task_runner.worktree.lifecycle.create_worktree",
        new_callable=AsyncMock,
        return_value=error,
    ):
        resolved = await resolve_workspace(store, task)
    assert resolved == str(base)
    assert await _branch_events(store, task.task_id) == []
