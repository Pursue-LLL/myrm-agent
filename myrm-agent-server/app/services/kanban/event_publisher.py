"""Kanban SSE event publishing helpers."""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

_BTW_TERMINAL_EVENTS = frozenset({"task_completed", "task_failed"})


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
    if meta.get("background_source") != "btw":
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
                "locale": meta.get("locale", "en"),
            },
        )
    )
