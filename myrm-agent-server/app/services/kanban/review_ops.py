"""Kanban IN_REVIEW approval/rejection orchestration.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- dependency_ops (POS: Dependency graph operations.)
- event_publisher (POS: Kanban SSE event publishing helpers.)

[OUTPUT]
- approve_task, reject_task

[POS]
Human-in-the-loop review transitions for require_approval tasks: approve
promotes to COMPLETED, reject sends back to READY for rework.
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskStatus,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.dependency_ops import promote_dependents
from app.services.kanban.event_publisher import publish_kanban_event


async def approve_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
    *,
    approver: str | None = None,
) -> KanbanTask | None:
    """Approve an IN_REVIEW task: promote to COMPLETED and release dependents.

    Delegates to the board dispatcher (source of truth for the state machine).
    Falls back to a direct store transition when no dispatcher is running.
    """
    task = await store.get_task(task_id)
    if task is None:
        return None
    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        return await dispatcher.approve_task(task_id, approver=approver)

    if task.status != TaskStatus.IN_REVIEW:
        raise ValueError(
            f"Cannot approve task in status '{task.status.value}'; only IN_REVIEW tasks can be approved"
        )
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    await store.save_task(task)
    await store.append_event(
        task_id,
        TaskEventKind.APPROVED,
        payload={"approver": approver or "human"},
    )
    await promote_dependents(store, task_id)
    publish_kanban_event(
        task.board_id,
        task_id,
        "approved",
        title=task.title,
        detail=task.result or "",
        status=task.status.value,
    )
    return task


async def reject_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
    *,
    reason: str,
    approver: str | None = None,
) -> KanbanTask | None:
    """Reject an IN_REVIEW task: send it back to READY for rework.

    The rejection reason is persisted on the event trail and echoed into the
    worker context (via prior-attempt error) so a re-run adapts.
    """
    task = await store.get_task(task_id)
    if task is None:
        return None
    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        return await dispatcher.reject_task(task_id, reason=reason, approver=approver)

    if task.status != TaskStatus.IN_REVIEW:
        raise ValueError(
            f"Cannot reject task in status '{task.status.value}'; only IN_REVIEW tasks can be rejected"
        )
    task.status = TaskStatus.READY
    task.error = reason
    task.consecutive_failures = 0
    await store.save_task(task)
    await store.append_event(
        task_id,
        TaskEventKind.REJECTED,
        payload={"reason": reason, "approver": approver or "human"},
    )
    publish_kanban_event(
        task.board_id,
        task_id,
        "rejected",
        title=task.title,
        detail=reason,
        status=task.status.value,
    )
    return task
