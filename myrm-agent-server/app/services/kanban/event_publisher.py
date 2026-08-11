"""Kanban SSE event publishing helpers.

[INPUT]
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- app.services.event.app_event_bus (POS: Global SSE event bus.)
- app.core.channel_bridge.persistent_background (POS: Background task source constants.)

[OUTPUT]
- publish_kanban_event, emit_btw_done, emit_review_requested, emit_task_rejected, emit_source_chat_done (completed/failed/blocked; skips scheduled blocks)

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

_TERMINAL_EVENTS = frozenset({"task_completed", "task_failed", "task_blocked"})


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


def _build_background_done_payload(
    task: KanbanTask,
    *,
    status: str,
    result: str,
) -> dict[str, object] | None:
    """Build a BACKGROUND_TASK_DONE payload for the task's originating chat.

    Routes to the /btw channel metadata when present, otherwise to the task's
    ``source_chat_id``. Returns None when the task has no delivery target.
    """
    meta = task.metadata or {}
    common: dict[str, object] = {
        "task_id": task.task_id,
        "board_id": task.board_id,
        "status": status,
        "title": task.title,
        "result": result,
        "locale": _task_locale(meta),
        "user_id": str(meta.get("user_id", "") or ""),
    }
    if meta.get("background_source") == BACKGROUND_SOURCE_BTW:
        channel = meta.get("channel")
        chat_id = meta.get("chat_id")
        if not channel or not chat_id:
            return None
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
            return None
        common.update(
            {
                "source_chat_id": source_chat_id,
                "chat_id": source_chat_id,
                "background_source": str(meta.get("background_source", "") or ""),
            }
        )
    return common


def _publish_background_done(payload: dict[str, object]) -> None:
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data=payload,
        )
    )


def emit_btw_done(event_type: str, task: KanbanTask) -> None:
    """Publish BACKGROUND_TASK_DONE when a /btw task reaches a terminal state."""
    if event_type not in _TERMINAL_EVENTS:
        return
    meta = task.metadata or {}
    if meta.get("background_source") != BACKGROUND_SOURCE_BTW:
        return
    status = _terminal_status(event_type, task)
    if status is None:
        return
    payload = _build_background_done_payload(
        task,
        status=status,
        result=_terminal_result(task, status),
    )
    if payload:
        _publish_background_done(payload)


def _task_locale(meta: dict[str, object]) -> str:
    """Best-effort locale from task metadata, falling back to English."""
    raw = meta.get("locale")
    return raw if isinstance(raw, str) and raw.strip() else "en"


def _publish_task_notice(task: KanbanTask, *, status: str, result: str) -> None:
    """Publish a BACKGROUND_TASK_DONE notice to the task's originating chat.

    Routes to the /btw channel metadata when present, otherwise to the task's
    ``source_chat_id``. Review states publish web pushes too — their titles are
    resolved from ``status`` by the web push layer, so they are never mistaken
    for a generic completion.
    """
    payload = _build_background_done_payload(
        task,
        status=status,
        result=result,
    )
    if payload:
        _publish_background_done(payload)


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
    _publish_task_notice(
        task, status="rejected", result=task.error or task.result or ""
    )


def _terminal_status(event_type: str, task: KanbanTask) -> str | None:
    """Map a dispatcher terminal event to a BACKGROUND_TASK_DONE status.

    SCHEDULED blocks (transient errors with auto-retry) are not terminal:
    the task wakes itself later, so no user notification is published.
    """
    if event_type == "task_completed":
        return "completed"
    if event_type == "task_failed":
        return "failed"
    if event_type == "task_blocked":
        if task.block_kind == BlockKind.SCHEDULED:
            return None
        return "blocked"
    return None


def _terminal_result(task: KanbanTask, status: str) -> str:
    if status == "blocked":
        return task.blocked_reason or task.error or ""
    return task.result or task.error or ""


def emit_source_chat_done(event_type: str, task: KanbanTask) -> None:
    """Publish BACKGROUND_TASK_DONE when a kanban task with source_chat_id terminates."""
    if event_type not in _TERMINAL_EVENTS:
        return
    status = _terminal_status(event_type, task)
    if status is None:
        return
    meta = task.metadata or {}
    if meta.get("background_source") == BACKGROUND_SOURCE_BTW:
        return
    payload = _build_background_done_payload(
        task,
        status=status,
        result=_terminal_result(task, status),
    )
    if payload:
        _publish_background_done(payload)
