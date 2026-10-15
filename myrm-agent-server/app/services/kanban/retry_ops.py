"""Kanban FAILED-task manual retry orchestration.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- event_publisher (POS: Kanban SSE event publishing helpers.)

[OUTPUT]
- retry_task: Operator-driven FAILED → READY retry.

[POS]
Human-in-the-loop recovery for tasks that exhausted their retry budget: the
operator decides to run the task again with a fresh budget.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.retry import retry_failed_task
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.event_publisher import publish_kanban_event


async def retry_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
) -> KanbanTask | None:
    """Retry a FAILED task: reset it to READY with a fresh retry budget.

    Delegates to the board dispatcher (it emits the SSE event and wakes the
    scheduler). Without a running dispatcher the harness retry runs directly and
    the SSE event is published here. Non-FAILED tasks are returned unchanged
    (idempotent double-submit); a missing task returns None.
    """
    task = await store.get_task(task_id)
    if task is None:
        return None
    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        return (await dispatcher.retry_task(task_id, source="human")).task

    outcome = await retry_failed_task(store, task_id, source="human")
    if outcome.applied and outcome.task is not None:
        publish_kanban_event(
            outcome.task.board_id,
            task_id,
            "task_retrying",
            title=outcome.task.title,
            status=outcome.task.status.value,
        )
    return outcome.task
