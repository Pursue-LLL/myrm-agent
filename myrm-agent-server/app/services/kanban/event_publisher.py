"""Kanban SSE event publishing helpers.

[INPUT]
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- app.services.event.app_event_bus (POS: Global SSE event bus.)
- app.core.channel_bridge.persistent_background (POS: Background task source constants.)

[OUTPUT]
- publish_kanban_event, emit_btw_done, emit_review_requested, emit_task_rejected, emit_source_chat_done (completed/failed/blocked for source_chat; skips scheduled blocks)

[POS]
SSE event publishing for kanban task updates and BTW terminal events.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanTask,
    extract_source_chat_id,
)

from app.core.channel_bridge.persistent_background import (
    BACKGROUND_SOURCE_BTW,
)
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

_BTW_TERMINAL_EVENTS = frozenset({"task_completed", "task_failed"})
_SOURCE_CHAT_TERMINAL_EVENTS = frozenset(
    {"task_completed", "task_failed", "task_blocked"}
)


def publish_kanban_event(
    board_id: str,
    task_id: str,
    action: str,
    *,
    title: str = "",
    detail: str = "",
    status: str = "",
) -> None:
    """Publish a kanban task update event to the global SSE event bus."""
    data: dict[str, str] = {
        "board_id": board_id,
        "task_id": task_id,
        "action": action,
    }
    if title:
        data["title"] = title
    if detail:
        data["detail"] = detail
    if status:
        data["status"] = status
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data=data,
        )
    )


def emit_btw_done(event_type: str, task: KanbanTask) -> None:
    """Publish BACKGROUND_TASK_DONE when a /btw task reaches a terminal state."""
    if event_type not in _BTW_TERMINAL_EVENTS:
        return
    meta = task.metadata or {}
    if meta.get("background_source") != BACKGROUND_SOURCE_BTW:
        return
    channel = meta.get("channel")
    chat_id = meta.get("chat_id")
    if not channel or not chat_id:
        return
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": task.task_id,
                "status": "completed" if event_type == "task_completed" else "failed",
                "title": task.title,
                "result": task.result or task.error or "",
                "channel": channel,
                "chat_id": chat_id,
                "thread_id": meta.get("thread_id", ""),
                "user_id": meta.get("user_id", ""),
                "locale": _task_locale(meta),
            },
        )
    )


def _task_locale(meta: dict[str, object]) -> str:
    """Best-effort locale from task metadata, falling back to English."""
    raw = meta.get("locale")
    return raw if isinstance(raw, str) and raw.strip() else "en"


def _publish_task_notice(task: KanbanTask, *, status: str, result: str) -> None:
    """Publish a BACKGROUND_TASK_DONE notice to the task's originating chat.

    Routes to the /btw channel metadata when present, otherwise to the task's
    ``source_chat_id``. Non-terminal statuses suppress the generic "Task
    Completed" web push; IM / btw notifiers handle delivery instead.
    """
    meta = task.metadata or {}
    common: dict[str, object] = {
        "task_id": task.task_id,
        "status": status,
        "title": task.title,
        "result": result,
        "locale": _task_locale(meta),
        "user_id": str(meta.get("user_id", "") or ""),
        "suppress_web_push": True,
    }
    if meta.get("background_source") == BACKGROUND_SOURCE_BTW:
        channel = meta.get("channel")
        chat_id = meta.get("chat_id")
        if not channel or not chat_id:
            return
        common.update(
            {
                "channel": str(channel),
                "chat_id": str(chat_id),
                "thread_id": str(meta.get("thread_id", "") or ""),
                "background_source": BACKGROUND_SOURCE_BTW,
            }
        )
    else:
        source_chat_id = extract_source_chat_id(meta)
        if not source_chat_id:
            return
        common.update({"source_chat_id": source_chat_id, "chat_id": source_chat_id})
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data=common,
        )
    )


def emit_review_requested(task: KanbanTask) -> None:
    """Notify the originating chat or /btw channel that a task awaits review.

    Published when the dispatcher moves a task to IN_REVIEW so the source-chat
    or /btw user can act promptly instead of the task sitting in review unnoticed.
    """
    _publish_task_notice(task, status="pending_review", result=task.result or "")


def emit_task_rejected(task: KanbanTask) -> None:
    """Notify the originating chat or /btw channel that a task was rejected.

    Published when the dispatcher rejects an IN_REVIEW task so the source-chat
    or /btw user learns the rework reason instead of silently waiting for the
    next attempt. The rejection reason is carried in ``task.error``.
    """
    _publish_task_notice(task, status="rejected", result=task.error or task.result or "")


def _source_chat_terminal_status(event_type: str, task: KanbanTask) -> str | None:
    """Map dispatcher terminal events to IM notification status."""
    if event_type == "task_completed":
        return "completed"
    if event_type == "task_failed":
        return "failed"
    if event_type == "task_blocked":
        if task.block_kind == BlockKind.SCHEDULED:
            return None
        return "blocked"
    return None


def _source_chat_terminal_result(task: KanbanTask, status: str) -> str:
    if status == "blocked":
        return task.blocked_reason or task.error or ""
    return task.result or task.error or ""


def emit_source_chat_done(event_type: str, task: KanbanTask) -> None:
    """Publish BACKGROUND_TASK_DONE when a kanban task with source_chat_id terminates."""
    if event_type not in _SOURCE_CHAT_TERMINAL_EVENTS:
        return
    status = _source_chat_terminal_status(event_type, task)
    if status is None:
        return
    meta = task.metadata or {}
    if meta.get("background_source") == BACKGROUND_SOURCE_BTW:
        return
    source_chat_id = extract_source_chat_id(meta)
    if not source_chat_id:
        return
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": task.task_id,
                "status": status,
                "title": task.title,
                "result": _source_chat_terminal_result(task, status),
                "chat_id": source_chat_id,
                "source_chat_id": source_chat_id,
                "thread_id": "",
                "user_id": str(meta.get("user_id", "") or ""),
                "locale": _task_locale(meta),
                "background_source": str(meta.get("background_source", "") or ""),
            },
        )
    )
