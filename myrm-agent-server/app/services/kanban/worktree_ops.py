"""Kanban task worktree lifecycle operations.

[INPUT]
- myrm_agent_harness.api::track_background_task (POS: Public API; graceful-shutdown task tracker.)
- myrm_agent_harness.toolkits.kanban.protocols::TaskRunner (POS: Task runner protocol.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskEventKind (POS: Kanban task and event types.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)

[OUTPUT]
- cleanup_task_worktree, merge_task_worktree, spawn_worktree_op

[POS]
Task worktree lifecycle management: cleaning up worktrees upon archiving and merging completed task branches.
Git work scales with repository size (seconds per task on a large tree), so callers that answer a user request
hand it to ``spawn_worktree_op`` instead of awaiting it. At most ``_MAX_CONCURRENT_GIT_OPS`` runner calls are in
flight at once, however many tasks were queued.
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

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner

    from app.core.kanban.adapters import SqlAlchemyKanbanStore

logger = logging.getLogger(__name__)

# Runner calls spend their time in the shared default thread pool and in git child processes. A bulk action queues
# one per card, and letting them all start at once slows the very request that queued them, so only a few run at a time.
_MAX_CONCURRENT_GIT_OPS = 2

# An asyncio primitive binds to the loop that first waits on it, so each loop gets its own semaphore.
_git_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = weakref.WeakKeyDictionary()


def _git_slot() -> asyncio.Semaphore:
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
            async with _git_slot():
                removed: bool = await runner.cleanup_worktree(task)
            return removed
        except Exception as exc:
            logger.warning(
                "Worktree cleanup failed for task %s: %s",
                task.task_id[:8],
                exc,
            )
    return True


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
        async with _git_slot():
            merged, conflicts = await runner.merge_task_worktree(task)
        if merged:
            return True, []
        logger.warning(
            "Merge skipped or conflicted for task %s; worktree preserved",
            task.task_id[:8],
        )
        if store is not None:
            payload: dict[str, object] = {
                "branch": task.branch,
                "message": (
                    "Task completed but the worktree merge was blocked; "
                    "code was not merged into the target branch. "
                    "Resolve the conflict or preserved worktree manually."
                ),
            }
            if conflicts:
                payload["conflicts"] = conflicts
            await store.append_event(
                task.task_id,
                TaskEventKind.MERGE_CONFLICT,
                payload=payload,
            )
        return False, conflicts
    except Exception as exc:
        logger.warning(
            "Worktree merge failed for task %s: %s",
            task.task_id[:8],
            exc,
        )
        if store is not None:
            await store.append_event(
                task.task_id,
                TaskEventKind.MERGE_CONFLICT,
                payload={
                    "branch": task.branch,
                    "message": f"Worktree merge failed: {exc}",
                },
            )
        return False, []


def spawn_worktree_op(operation: Coroutine[object, object, object]) -> None:
    """Run a worktree operation after the request has been answered.

    The harness tracker keeps the task referenced (the event loop alone holds only a weak reference) and lets
    graceful shutdown wait for it. Nothing awaits the task, so a failure is logged here instead of vanishing.
    """

    async def run() -> None:
        try:
            await operation
        except Exception:
            logger.exception("Background worktree operation failed")

    track_background_task(asyncio.get_running_loop().create_task(run()))
