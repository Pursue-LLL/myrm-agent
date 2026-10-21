"""Run-entry gate: a dependent task waits for the user when a completed parent's code never landed on its branch.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports; KanbanStore defined in toolkits.kanban.protocols.)
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- app.services.kanban.worktree_landing::wait_parents_landed (POS: 等待进行中的父任务 merge 落地)
- worktree.lifecycle::resolve_base_dir (POS: 任务所在仓库目录)

[OUTPUT]
- PARENT_MERGE_FAILED_REASON, ACKNOWLEDGED_MERGE_FAILURE_KEY, hold_for_unlanded_parents

[POS]
A completed task's merge runs in the background and records a MERGE_CONFLICT event when its code could not be
merged (``worktree_ops.record_merge_failure``). The dispatcher still starts the task's dependents, which would then
build on a repository without that code and, once they finish, merge their own work on top of it without review.
This gate runs first in ``KanbanTaskRunner.run``, before any context is built, so a held dependent costs no model
call and leaves the prompt of the run that follows untouched. It returns a HUMAN block; unblocking the task is the
user's acknowledgement, recorded as the newest failure id they have seen, so the same failure never holds it twice.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanTask,
    TaskEventKind,
    TaskExecutionResult,
    TaskStatus,
)

from app.services.kanban.task_runner.worktree.lifecycle import resolve_base_dir
from app.services.kanban.worktree_landing import wait_parents_landed

logger = logging.getLogger(__name__)

# The frontend translates this exact sentence (shared/config/kanban_blocked_reasons.json, kept equal by
# test_blocked_reason_contract); other consumers show it as written.
PARENT_MERGE_FAILED_REASON = "Merging a dependency's changes failed; resolve it, then continue"
ACKNOWLEDGED_MERGE_FAILURE_KEY = "acknowledged_merge_failure_event_id"


async def _newest_merge_failure(store: KanbanStore, task_id: str) -> int:
    """Id of the task's newest MERGE_CONFLICT event; 0 when it has none, i.e. its code landed or is still merging.

    A completed task can never be completed again (shared/config/kanban_move_guard.json), so no later completion
    supersedes a recorded failure.
    """
    events = await store.list_events(task_id)
    return max((event.event_id for event in events if event.kind == TaskEventKind.MERGE_CONFLICT), default=0)


async def hold_for_unlanded_parents(store: KanbanStore, task: KanbanTask) -> TaskExecutionResult | None:
    """Return the block that holds ``task`` back, or None when it may run.

    Only completed parents with a branch in the task's own repository count: a parent without a branch never merges,
    and a merge in another repository changes nothing the task builds on.
    """
    await wait_parents_landed(store, task)
    parent_ids = await store.list_parents(task.task_id)
    if not parent_ids:
        return None
    base_dir = await resolve_base_dir(store, task)
    if base_dir is None:
        return None

    newest_failure = 0
    for parent_id in parent_ids:
        parent = await store.get_task(parent_id)
        if parent is None or parent.status != TaskStatus.COMPLETED or not parent.branch:
            continue
        if await resolve_base_dir(store, parent) != base_dir:
            continue
        newest_failure = max(newest_failure, await _newest_merge_failure(store, parent_id))

    acknowledged = task.metadata.get(ACKNOWLEDGED_MERGE_FAILURE_KEY)
    if newest_failure <= (acknowledged if isinstance(acknowledged, int) else 0):
        return None
    logger.info("Task %s is held: a parent's merge failure (event %d) is not acknowledged", task.task_id[:8], newest_failure)
    return TaskExecutionResult.blocked(
        PARENT_MERGE_FAILED_REASON,
        block_kind=BlockKind.HUMAN,
        metadata_patch={ACKNOWLEDGED_MERGE_FAILURE_KEY: newest_failure},
    )
