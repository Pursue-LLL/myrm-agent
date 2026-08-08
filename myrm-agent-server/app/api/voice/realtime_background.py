"""Realtime voice background task lifecycle handlers.

Short-circuit handlers for background task tools (run/cancel/status/steer)
invoked from the OpenAI Realtime WebRTC session. Each handler delegates to
ChannelBackgroundTaskHandler without invoking the full Agent pipeline.

[INPUT]
- app.core.channel_bridge.setup::get_background_task_handler (POS: Channel gateway lifecycle)
- app.core.channel_bridge.persistent_background (POS: metadata SSOT)

[OUTPUT]
- BACKGROUND_TOOL_HANDLERS: dict mapping tool names to async handler functions
- RealtimeToolExecRequest, RealtimeToolExecResponse re-exported for convenience

[POS]
Voice background task lifecycle. Extracted from realtime.py to keep file sizes
manageable. All handlers return RealtimeToolExecResponse directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.api.voice.realtime import RealtimeToolExecRequest, RealtimeToolExecResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.channels.types import InboundMessage
    from app.core.channel_bridge.background_task_handler import (
        ChannelBackgroundTaskHandler,
    )

_RUN_BACKGROUND_TASK_NAME = "run_background_task"
_CANCEL_BACKGROUND_TASK_NAME = "cancel_background_task"
_GET_BACKGROUND_TASKS_STATUS_NAME = "get_background_tasks_status"
_STEER_BACKGROUND_TASK_NAME = "steer_background_task"


def _build_voice_inbound_msg(req: RealtimeToolExecRequest) -> "InboundMessage":
    """Build an InboundMessage for voice background task lifecycle operations."""
    from app.channels.types import InboundMessage

    chat_id = req.chat_id or "realtime-voice"
    return InboundMessage(
        channel="realtime_voice",
        sender_id=chat_id,
        chat_id=chat_id,
        content="",
        user_id="local-user",
    )


def _get_handler() -> ChannelBackgroundTaskHandler | None:
    from app.core.channel_bridge.setup import get_background_task_handler

    return get_background_task_handler()


_NO_HANDLER = RealtimeToolExecResponse(result=None, error="Background task handler not available")


async def _execute_cancel_background_task(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Cancel a running background task by task_id."""
    task_id = str(req.arguments.get("task_id", "")).strip()
    if not task_id:
        return RealtimeToolExecResponse(result=None, error="task_id is required")

    handler = _get_handler()
    if handler is None:
        return _NO_HANDLER

    success = await handler.cancel_background(_build_voice_inbound_msg(req), task_id)
    if not success:
        return RealtimeToolExecResponse(result=None, error="Task not found or not cancellable")

    return RealtimeToolExecResponse(result=json.dumps({"cancelled": True, "task_id": task_id}))


async def _execute_get_background_tasks_status(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Return status of all persistent background tasks."""
    handler = _get_handler()
    if handler is None:
        return _NO_HANDLER

    task_infos = await handler.list_background(_build_voice_inbound_msg(req))
    tasks_payload = [
        {
            "task_id": t.task_id,
            "prompt": t.prompt[:80],
            "status": t.status,
            "created_at": t.created_at,
            "completed_at": t.completed_at,
            "result_preview": t.result_preview,
        }
        for t in task_infos
    ]
    return RealtimeToolExecResponse(result=json.dumps({"tasks": tasks_payload, "count": len(tasks_payload)}))


async def _execute_steer_background_task(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Inject a steering instruction into a running background task."""
    task_id = str(req.arguments.get("task_id", "")).strip()
    instruction = str(req.arguments.get("instruction", "")).strip()
    if not task_id or not instruction:
        return RealtimeToolExecResponse(result=None, error="task_id and instruction are required")

    handler = _get_handler()
    if handler is None:
        return _NO_HANDLER

    success = await handler.steer_background(_build_voice_inbound_msg(req), task_id, instruction)
    if not success:
        return RealtimeToolExecResponse(result=None, error="Task not found or not running")

    return RealtimeToolExecResponse(result=json.dumps({"steered": True, "task_id": task_id}))


async def _execute_run_background_task(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Non-blocking accept: spawn Kanban work and return immediately."""
    from app.channels.types import InboundMessage
    from app.core.channel_bridge.persistent_background import BACKGROUND_SOURCE_VOICE

    task_text = str(req.arguments.get("task", "")).strip()
    if not task_text:
        return RealtimeToolExecResponse(result=None, error="Task description is required")

    if not req.chat_id:
        return RealtimeToolExecResponse(
            result=None,
            error="Please open a chat first. Background tasks need an active conversation to deliver results.",
        )

    handler = _get_handler()
    if handler is None:
        return _NO_HANDLER

    agent_id = req.agent_id or "builtin-general"
    chat_id = req.chat_id
    msg = InboundMessage(
        channel="realtime_voice",
        sender_id=chat_id,
        chat_id=chat_id,
        content=task_text,
        user_id="local-user",
    )

    try:
        task_id = await handler.spawn_background(
            msg,
            task_text,
            background_source=BACKGROUND_SOURCE_VOICE,
            agent_id=agent_id,
        )
    except RuntimeError as exc:
        return RealtimeToolExecResponse(result=None, error=str(exc))

    payload = {
        "accepted": True,
        "work_id": task_id,
        "message": "Background task accepted. Continue the conversation; results will appear in chat when done.",
    }
    return RealtimeToolExecResponse(result=json.dumps(payload))


BACKGROUND_TOOL_HANDLERS: dict[str, Callable[[RealtimeToolExecRequest], Awaitable[RealtimeToolExecResponse]]] = {
    _RUN_BACKGROUND_TASK_NAME: _execute_run_background_task,
    _CANCEL_BACKGROUND_TASK_NAME: _execute_cancel_background_task,
    _GET_BACKGROUND_TASKS_STATUS_NAME: _execute_get_background_tasks_status,
    _STEER_BACKGROUND_TASK_NAME: _execute_steer_background_task,
}
