"""Merges of completed tasks that are still in flight, so a dependent starts from the code its parents produced.

[INPUT]
- myrm_agent_harness.api::KanbanStore (POS: Public protocol re-exports; KanbanStore defined in toolkits.kanban.protocols.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Kanban domain types.)

[OUTPUT]
- register_landing, wait_parents_landed

[POS]
A dependent's worktree is cut from the repository as it is when the dependent starts. The dispatcher releases a
dependent as soon as its parent completes, while the parent's merge still runs in the background, so the dependent
would start from a repository without the parent's work. ``worktree_ops.spawn_worktree_op`` registers each such merge
here under the completed task's id; ``task_runner.worktree.lifecycle.resolve_workspace`` waits for the merges of the
task's parents before it resolves the workspace. Nothing is persisted: a restart loses the merge itself, so there is
nothing left to wait for.
"""

from __future__ import annotations

import asyncio
import logging
import weakref

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

logger = logging.getLogger(__name__)

# Longer than the slowest git step of a merge (its own 60 s timeout), so a healthy merge always finishes inside it,
# while a hung git cannot hold a dependent back for good.
_LANDING_WAIT_SECONDS = 120.0

# Keyed by task id; completing the same task again replaces its entry while the earlier merge keeps running (merges
# of one repository are serialized anyway). An asyncio task belongs to one loop, so each loop gets its own table.
_landings: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Task[None]]] = weakref.WeakKeyDictionary()


def _loop_landings() -> dict[str, asyncio.Task[None]]:
    loop = asyncio.get_running_loop()
    landings = _landings.get(loop)
    if landings is None:
        landings = _landings[loop] = {}
    return landings


def register_landing(task_id: str, merge: asyncio.Task[None]) -> None:
    """Record ``merge`` as the in-flight merge of the completed task ``task_id`` until it finishes."""
    landings = _loop_landings()
    landings[task_id] = merge

    def forget(finished: asyncio.Task[None]) -> None:
        if landings.get(task_id) is finished:
            del landings[task_id]

    merge.add_done_callback(forget)


async def wait_parents_landed(store: KanbanStore, task: KanbanTask) -> None:
    """Wait until every parent of ``task`` that is still merging has finished merging.

    Returns at once, without reading the store, when no merge is in flight. A merge that fails still ends the wait:
    its failure is recorded on the parent, and ``task_runner.worktree.landing_gate`` decides from that record whether
    the dependent may run. A merge that outlasts ``_LANDING_WAIT_SECONDS`` is left running and the dependent starts
    anyway.
    """
    landings = _loop_landings()
    if not landings:
        return
    parent_ids = await store.list_parents(task.task_id)
    pending = {merge for parent_id in parent_ids if (merge := landings.get(parent_id)) is not None}
    if not pending:
        return
    logger.info("Task %s waits for %d parent merge(s) to land", task.task_id[:8], len(pending))
    # ``asyncio.wait`` leaves the awaited merges alone when it times out or the waiter is cancelled; ``wait_for`` would
    # cancel them mid-merge.
    _, unfinished = await asyncio.wait(pending, timeout=_LANDING_WAIT_SECONDS)
    if unfinished:
        logger.warning(
            "Task %s starts while %d parent merge(s) are still running after %.0f s",
            task.task_id[:8],
            len(unfinished),
            _LANDING_WAIT_SECONDS,
        )
