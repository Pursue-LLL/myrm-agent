"""Kanban task worktree lifecycle operations.

[INPUT]
- myrm_agent_harness.api::track_background_task (POS: Public API; graceful-shutdown task tracker.)
- myrm_agent_harness.toolkits.kanban.protocols::TaskRunner (POS: Task runner protocol.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskEventKind (POS: Kanban task and event types.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- worktree_landing::register_landing (POS: In-flight merges of completed tasks, awaited by their dependents.)

[OUTPUT]
- cleanup_task_worktree, merge_task_worktree, record_merge_failure, spawn_worktree_op, git_slot

[POS]
Task worktree lifecycle management: cleaning up worktrees upon archiving and merging completed task branches.
Git work scales with repository size (seconds per task on a large tree), so callers that answer a user request
hand it to ``spawn_worktree_op`` instead of awaiting it. Work started that way waits on ``git_slot`` first, so at
most ``_MAX_CONCURRENT_GIT_OPS`` of it runs at once however many tasks were queued; the dispatcher's own merges do
not wait on it. A merge spawned for a completed task is registered with ``worktree_landing`` so that the task's
dependents wait for it before they build their workspace.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import Coroutine
from typing import TYPE_CHECKING

from myrm_agent_harness.api import track_background_task
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
)

from app.services.kanban.worktree_landing import register_landing

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner

    from app.core.kanban.adapters import SqlAlchemyKanbanStore

logger = logging.getLogger(__name__)

# Background worktree work spends its time in the shared default thread pool and in git child processes. A bulk
# action queues one operation per card, and letting them all start at once slows the very request that queued
# them, so only a few run at a time.
_MAX_CONCURRENT_GIT_OPS = 2

# An asyncio primitive binds to the loop that first waits on it, so each loop gets its own semaphore.
_git_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


def git_slot() -> asyncio.Semaphore:
    """Limit on background worktree operations running git at the same time.

    A caller that answers a request holds it around the runner call (``async with git_slot():``) inside its own
    try/finally. The dispatcher's merges do not use it: they must not queue behind a bulk action.
    """
    loop = asyncio.get_running_loop()
    slot = _git_slots.get(loop)
    if slot is None:
        slot = _git_slots[loop] = asyncio.Semaphore(_MAX_CONCURRENT_GIT_OPS)
    return slot


async def cleanup_task_worktree(
    runner: TaskRunner | None,
    task: KanbanTask,
) -> bool:
    """Delegate worktree cleanup to the runner if it supports it.

    Returns True when the worktree was removed or absent.  Returns False when
    the runner preserved a dirty worktree (uncommitted agent edits) — the
    caller should surface this instead of pretending cleanup succeeded.
    """
    if runner is not None and hasattr(runner, "cleanup_worktree"):
        try:
            removed: bool = await runner.cleanup_worktree(task)
            return removed
        except Exception as exc:
            logger.warning(
                "Worktree cleanup failed for task %s: %s",
                task.task_id[:8],
                exc,
            )
    return True


async def record_merge_failure(
    store: SqlAlchemyKanbanStore,
    task: KanbanTask,
    message: str,
    conflicts: list[str] | None = None,
) -> None:
    """Record that a completed task's code did not land on its branch, so the board can show it."""
    payload: dict[str, object] = {"branch": task.branch, "message": message}
    if conflicts:
        payload["conflicts"] = conflicts
    await store.append_event(task.task_id, TaskEventKind.MERGE_CONFLICT, payload=payload)


async def merge_task_worktree(
    runner: TaskRunner | None,
    task: KanbanTask,
    store: SqlAlchemyKanbanStore | None = None,
) -> tuple[bool, list[str]]:
    """Merge a completed task's worktree commits into its target branch.

    Returns (success, conflict_files).  On failure (conflict, uncommittable
    changes, unusable branch) the worktree is preserved; when a ``store`` is
    given, a MERGE_CONFLICT event is appended (with the conflicting file paths
    when known) so the user can see the completed task's code never landed on
    its branch.
    """
    if runner is None or not hasattr(runner, "merge_task_worktree"):
        return True, []
    try:
        merged, conflicts = await runner.merge_task_worktree(task)
        if merged:
            return True, []
        logger.warning(
            "Merge skipped or conflicted for task %s; worktree preserved",
            task.task_id[:8],
        )
        if store is not None:
            await record_merge_failure(
                store,
                task,
                "Task completed but the worktree merge was blocked; "
                "code was not merged into the target branch. "
                "Resolve the conflict or preserved worktree manually.",
                conflicts,
            )
        return False, conflicts
    except Exception as exc:
        logger.warning(
            "Worktree merge failed for task %s: %s",
            task.task_id[:8],
            exc,
        )
        if store is not None:
            await record_merge_failure(store, task, f"Worktree merge failed: {exc}")
        return False, []


def spawn_worktree_op(operation: Coroutine[object, object, object], *, lands: str | None = None) -> None:
    """Run a worktree operation after the request has been answered.

    The harness tracker keeps the task referenced (the event loop alone holds only a weak reference) and lets
    graceful shutdown wait for it. Nothing awaits the task, so a failure is logged here instead of vanishing.
    ``lands`` is the id of the completed task whose merge ``operation`` performs: until it finishes, the task's
    dependents wait before they build their workspace.
    """

    async def run() -> None:
        try:
            await operation
        except Exception:
            logger.exception("Background worktree operation failed")

    background = asyncio.get_running_loop().create_task(run())
    track_background_task(background)
    if lands is not None:
        register_landing(lands, background)
