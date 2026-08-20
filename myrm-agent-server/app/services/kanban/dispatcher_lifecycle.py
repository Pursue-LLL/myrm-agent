"""Kanban dispatcher lifecycle and boot recovery.

[INPUT]
- myrm_agent_harness.toolkits.kanban.dispatcher (POS: Kanban dispatcher framework.)
- myrm_agent_harness.toolkits.kanban.protocols (POS: Kanban protocol interfaces.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- event_publisher (POS: Kanban SSE event publishing helpers.)
- move_orchestrator.merge_task_worktree (POS: Completed-task worktree merge back to target branch.)

[OUTPUT]
- recover_stale_tasks, start_dispatcher, stop_dispatcher, shutdown_dispatchers, _make_task_completed_merge_hook

[POS]
Dispatcher lifecycle: boot recovery, start/stop per-board dispatchers, graceful shutdown. Registers a task_completed hook that schedules async worktree merge (sync dispatcher emit → background task) so auto-completed tasks land their commits on the target branch.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.batch_directory import BatchDirectoryService
from app.services.kanban.event_publisher import (
    emit_btw_done,
    emit_review_requested,
    emit_source_chat_done,
    emit_task_rejected,
    publish_kanban_event,
)
from app.services.kanban.move_orchestrator import merge_task_worktree

logger = logging.getLogger(__name__)


async def recover_stale_tasks(store: SqlAlchemyKanbanStore) -> int:
    """Reset RUNNING tasks to READY on server boot."""
    count = await store.reset_stale_running_tasks()
    if count > 0:
        logger.info("[Boot Recovery] Reset %d stale RUNNING tasks to READY", count)
    return count


def _make_task_completed_merge_hook(runner: TaskRunner, store: SqlAlchemyKanbanStore):
    """Synchronous dispatcher callback that schedules async worktree merge.

    Dispatcher emits are synchronous, so the actual merge runs in a
    background task.  merge_task_worktree is idempotent — when the worktree
    is already gone (manual move path already merged it) it is a no-op.
    """

    def hook(event_type: str, task: KanbanTask) -> None:
        if event_type != "task_completed":
            return
        try:
            asyncio.get_running_loop().create_task(merge_task_worktree(runner, task, store))
        except RuntimeError:  # pragma: no cover - 无事件循环时不调度
            logger.debug("No running loop; skip worktree merge for %s", task.task_id[:8])

    return hook


async def start_dispatcher(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
    runner: TaskRunner,
    worker_id: str | None = None,
) -> KanbanDispatcher | None:
    """Start a dispatcher for a board."""
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
    )
    dispatcher.on_event(
        lambda event_type, task: publish_kanban_event(
            task.board_id,
            task.task_id,
            event_type,
            title=task.title,
            detail=task.result or task.blocked_reason or task.error or "",
        )
    )
    dispatcher.on_event(emit_btw_done)
    dispatcher.on_event(emit_source_chat_done)
    dispatcher.on_event(lambda event_type, task: emit_review_requested(task) if event_type == "task_review_requested" else None)
    dispatcher.on_event(lambda event_type, task: emit_task_rejected(task) if event_type == "task_rejected" else None)
    dispatcher.on_event(BatchDirectoryService.get_instance().dispatcher_event_hook)
    dispatcher.on_event(_make_task_completed_merge_hook(runner, store))
    await dispatcher.start()
    dispatchers[board_id] = dispatcher
    logger.info("Started dispatcher for board %s", board_id)
    return dispatcher


async def stop_dispatcher(
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
) -> bool:
    if board_id not in dispatchers:
        return False
    await dispatchers[board_id].stop()
    del dispatchers[board_id]
    return True


async def shutdown_dispatchers(dispatchers: dict[str, KanbanDispatcher]) -> None:
    """Stop all dispatchers."""
    for board_id in list(dispatchers):
        await stop_dispatcher(dispatchers, board_id)
