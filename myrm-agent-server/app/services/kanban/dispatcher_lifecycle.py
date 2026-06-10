"""Kanban dispatcher lifecycle and boot recovery.

[INPUT]
- myrm_agent_harness.toolkits.kanban.dispatcher (POS: Kanban dispatcher framework.)
- myrm_agent_harness.toolkits.kanban.protocols (POS: Kanban protocol interfaces.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- event_publisher (POS: Kanban SSE event publishing helpers.)

[OUTPUT]
- recover_stale_tasks, start_dispatcher, stop_dispatcher, shutdown_dispatchers

[POS]
Dispatcher lifecycle: boot recovery, start/stop per-board dispatchers, graceful shutdown.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.event_publisher import emit_btw_done, publish_kanban_event

logger = logging.getLogger(__name__)


async def recover_stale_tasks(store: SqlAlchemyKanbanStore) -> int:
    """Reset RUNNING tasks to READY on server boot."""
    count = await store.reset_stale_running_tasks()
    if count > 0:
        logger.info("[Boot Recovery] Reset %d stale RUNNING tasks to READY", count)
    return count


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
