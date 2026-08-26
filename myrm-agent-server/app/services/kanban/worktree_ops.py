"""Kanban task worktree lifecycle operations.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskRunner (POS: Task runner protocol.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskEventKind (POS: Kanban task and event types.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)

[OUTPUT]
- cleanup_task_worktree, merge_task_worktree

[POS]
Task worktree lifecycle management: cleaning up worktrees upon archiving and merging completed task branches.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner

    from app.core.kanban.adapters import SqlAlchemyKanbanStore

logger = logging.getLogger(__name__)


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
            return await runner.cleanup_worktree(task)  # type: ignore[attr-defined]
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
        merged, conflicts = await runner.merge_task_worktree(task)  # type: ignore[attr-defined]
        if merged:
            return True, []
        logger.warning(
            "Merge skipped or conflicted for task %s; worktree preserved",
            task.task_id[:8],
        )
        if store is not None:
            payload: dict[str, str | list[str]] = {
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
