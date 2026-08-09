"""Kanban IN_REVIEW approval/rejection orchestration.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- dependency_ops (POS: Dependency graph operations.)
- event_publisher (POS: Kanban SSE event publishing helpers.)

[OUTPUT]
- approve_task, reject_task (with rejection notice via emit_task_rejected)

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
from app.services.kanban.event_publisher import (
    emit_btw_done,
    emit_source_chat_done,
    emit_task_rejected,
    publish_kanban_event,
)


async def approve_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
    *,
    approver: str | None = None,
) -> KanbanTask | None:
    """Approve an IN_REVIEW task: promote to COMPLETED and release dependents.

    Delegates to the board dispatcher (source of truth for the state machine).
    Falls back to an atomic CAS transition when no dispatcher is running.
    Non-IN_REVIEW tasks are returned unchanged (idempotent double-submit).
    """
    task = await store.get_task(task_id)
    if task is None:
        return None
    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        return await dispatcher.approve_task(task_id, approver=approver)

    task = await store.transition_task_status(
        task_id,
        TaskStatus.IN_REVIEW,
        TaskStatus.COMPLETED,
    )
    if task is None:
        return await store.get_task(task_id)
    task.completed_at = datetime.now(UTC)
    task.consecutive_failures = 0
    task.block_cycle_count = 0
    task.progress_note = None
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
        "task_completed",
        title=task.title,
        detail=task.result or "",
        status=task.status.value,
    )
    # Mirror the dispatcher's terminal event so btw / source-chat users
    # receive the completion notification even without a running dispatcher.
    emit_btw_done("task_completed", task)
    emit_source_chat_done("task_completed", task)
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
    Non-IN_REVIEW tasks are returned unchanged (idempotent double-submit).
    """
    task = await store.get_task(task_id)
    if task is None:
        return None
    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        return await dispatcher.reject_task(task_id, reason=reason, approver=approver)

    task = await store.transition_task_status(
        task_id,
        TaskStatus.IN_REVIEW,
        TaskStatus.READY,
    )
    if task is None:
        return await store.get_task(task_id)
    task.consecutive_failures = 0
    task.retry_count = 0
    task.error = reason
    task.last_heartbeat_at = None
    task.progress_note = None
    await store.save_task(task)
    await store.append_event(
        task_id,
        TaskEventKind.REJECTED,
        payload={
            "reason": reason,
            "approver": approver or "human",
            "from": TaskStatus.IN_REVIEW.value,
        },
    )
    publish_kanban_event(
        task.board_id,
        task_id,
        "task_rejected",
        title=task.title,
        detail=reason,
        status=task.status.value,
    )
    # Mirror the dispatcher's task_rejected event so btw / source-chat users
    # receive the rejection notice even without a running dispatcher.
    emit_task_rejected(task)
    return task
