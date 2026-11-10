"""Kanban dispatcher lifecycle and boot recovery.

[INPUT]
- myrm_agent_harness.toolkits.kanban.dispatcher (POS: Kanban dispatcher framework.)
- myrm_agent_harness.toolkits.kanban.protocols (POS: Kanban protocol interfaces.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- event_publisher (POS: Kanban SSE event publishing helpers.)
- worktree_ops::merge_task_worktree, spawn_worktree_op (POS: Completed-task worktree merge back to target branch; off-request worktree work.)

[OUTPUT]
- recover_stale_tasks, start_dispatcher, stop_dispatcher, shutdown_dispatchers, _make_task_completed_merge_hook

[POS]
Dispatcher lifecycle: boot recovery, start/stop per-board dispatchers, graceful concurrent shutdown. Registers a task_completed hook that schedules async worktree merge (sync dispatcher emit → tracked background task registered as the task's landing) so auto-completed tasks land their commits on the target branch before their dependents build a workspace.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.batch_directory import BatchDirectoryService
from app.services.kanban.event_publisher import (
    emit_btw_done,
    emit_review_requested,
    emit_source_chat_done,
    emit_task_rejected,
    publish_task_event,
)
from app.services.kanban.worktree_ops import merge_task_worktree, spawn_worktree_op

logger = logging.getLogger(__name__)


async def recover_stale_tasks(store: SqlAlchemyKanbanStore) -> int:
    """Reset RUNNING tasks to READY on server boot."""
    count = await store.reset_stale_running_tasks()
    if count > 0:
        logger.info("[Boot Recovery] Reset %d stale RUNNING tasks to READY", count)
    return count


def _make_task_completed_merge_hook(runner: TaskRunner, store: SqlAlchemyKanbanStore) -> Callable[[str, KanbanTask], None]:
    """Synchronous dispatcher callback that schedules async worktree merge.

    Dispatcher emits are synchronous (and run on the event loop), so the actual merge runs in a tracked
    background task, registered as the task's landing so its dependents wait for it before they build their
    workspace.  merge_task_worktree is idempotent — when the worktree
    is already gone (manual move path already merged it) it is a no-op.
    """

    def hook(event_type: str, task: KanbanTask) -> None:
        if event_type != "task_completed":
            return
        spawn_worktree_op(merge_task_worktree(runner, task, store), lands=task.task_id)

    return hook


async def start_dispatcher(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
    runner: TaskRunner,
    worker_id: str | None = None,
    *,
    rescue_orphans: bool = True,
    dispatch_allowed: Callable[[], Awaitable[bool]] | None = None,
    board: KanbanBoard | None = None,
) -> KanbanDispatcher | None:
    """Start a dispatcher for a board.

    ``dispatch_allowed`` is the boot gate: while it returns False the dispatcher leaves READY tasks
    queued instead of claiming and failing them. Callers that start a board at runtime (a user is
    present and can configure a provider) leave it None, so their behaviour is unchanged.

    ``board`` is the row the caller has just read; passing it spares one query per board when
    hundreds of boards start together.
    """
    if board is None:
        board = await store.get_board(board_id)
    if board is None:
        return None

    if board_id in dispatchers:
        await dispatchers[board_id].stop()

    from app.core.kanban.verifier import KanbanCompletionVerifier

    dispatcher = KanbanDispatcher(
        store=store,
        runner=runner,
        board=board,
        worker_id=worker_id,
        verifier=KanbanCompletionVerifier(),
        dispatch_allowed=dispatch_allowed,
    )
    dispatcher.on_event(publish_task_event)
    dispatcher.on_event(emit_btw_done)
    dispatcher.on_event(emit_source_chat_done)
    dispatcher.on_event(lambda event_type, task: emit_review_requested(task) if event_type == "task_review_requested" else None)
    dispatcher.on_event(lambda event_type, task: emit_task_rejected(task) if event_type == "task_rejected" else None)
    dispatcher.on_event(BatchDirectoryService.get_instance().dispatcher_event_hook)
    dispatcher.on_event(_make_task_completed_merge_hook(runner, store))
    await dispatcher.start(rescue_orphans=rescue_orphans)
    dispatchers[board_id] = dispatcher
    logger.info("Started dispatcher for board %s", board_id)
    return dispatcher


async def stop_dispatcher(
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
) -> bool:
    dispatcher = dispatchers.get(board_id)
    if dispatcher is None:
        return False
    await dispatcher.stop()
    # The board may have been started again while this one was stopping; only this dispatcher's entry goes.
    if dispatchers.get(board_id) is dispatcher:
        del dispatchers[board_id]
    return True


async def shutdown_dispatchers(dispatchers: dict[str, KanbanDispatcher]) -> None:
    """Stop every dispatcher at once, so that one slow board does not hold back the others.

    A stop lets the dispatcher's loops finish the database call they are in and may wait for running tasks;
    done one board after the other those waits would add up with the number of boards. A dispatcher that
    fails to stop is logged and left registered; the rest are stopped regardless.
    """
    board_ids = list(dispatchers)
    results = await asyncio.gather(*(stop_dispatcher(dispatchers, board_id) for board_id in board_ids), return_exceptions=True)
    for board_id, result in zip(board_ids, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Kanban dispatcher of board %s failed to stop: %s", board_id, result, exc_info=result)
