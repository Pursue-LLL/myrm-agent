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
_SET_REMINDER_NAME = "set_reminder"
_CANCEL_REMINDER_NAME = "cancel_reminder"
_LIST_REMINDERS_NAME = "list_reminders"


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


async def _execute_set_reminder(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Schedule a reminder directly via CronManager SSOT."""
    from datetime import datetime, timedelta, timezone
    from myrm_agent_harness.toolkits.cron.types import DeliveryConfig, JobType, Schedule, ScheduleKind
    from app.core.cron.adapters.setup import get_cron_manager

    content = str(req.arguments.get("content", "")).strip()
    if not content:
        return RealtimeToolExecResponse(result=None, error="Reminder content is required")

    minutes_val = req.arguments.get("minutes_later")
    schedule_time_val = req.arguments.get("schedule_time")

    now = datetime.now(timezone.utc)
    run_at: datetime | None = None

    if minutes_val is not None:
        try:
            delta_minutes = float(minutes_val)
            if delta_minutes <= 0:
                delta_minutes = 1.0
            run_at = now + timedelta(minutes=delta_minutes)
        except (ValueError, TypeError):
            pass

    if run_at is None and schedule_time_val:
        try:
            iso_str = str(schedule_time_val).strip()
            parsed = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            run_at = parsed
        except (ValueError, TypeError):
            pass

    if run_at is None:
        # Default fallback: 5 minutes later
        run_at = now + timedelta(minutes=5)

    name = f"Voice Reminder: {content[:40]}"
    mgr = get_cron_manager()

    try:
        job = await mgr.create_job(
            user_id="default",
            name=name,
            job_type=JobType.REMINDER,
            schedule=Schedule(kind=ScheduleKind.ONCE, run_at=run_at),
            prompt=content,
            chat_id=req.chat_id,
            delivery=DeliveryConfig(channel="chat"),
        )
        return RealtimeToolExecResponse(
            result=json.dumps(
                {
                    "success": True,
                    "job_id": job.id,
                    "name": job.name,
                    "content": content,
                    "scheduled_at": run_at.isoformat(),
                    "message": f"Reminder set for {run_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                }
            )
        )
    except Exception as exc:
        logger.exception("Failed to create voice reminder cron job: %s", exc)
        return RealtimeToolExecResponse(result=None, error=f"Failed to create reminder: {exc}")


async def _execute_cancel_reminder(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Cancel a scheduled reminder via CronManager."""
    from app.core.cron.adapters.setup import get_cron_manager
    from myrm_agent_harness.toolkits.cron.types import JobStatus, JobType

    reminder_id = str(req.arguments.get("reminder_id", "")).strip()
    content_query = str(req.arguments.get("content", "")).strip().lower()
    cancel_latest = bool(req.arguments.get("cancel_latest", False))

    mgr = get_cron_manager()
    try:
        jobs = await mgr.list_jobs("default")
        active_reminders = [
            j for j in jobs
            if j.status == JobStatus.ACTIVE and j.job_type == JobType.REMINDER
        ]

        target_job = None
        if reminder_id:
            for j in active_reminders:
                if j.id == reminder_id:
                    target_job = j
                    break
        elif content_query:
            for j in active_reminders:
                if content_query in j.name.lower() or (j.prompt and content_query in j.prompt.lower()):
                    target_job = j
                    break
        elif cancel_latest and active_reminders:
            target_job = active_reminders[-1]

        if not target_job:
            return RealtimeToolExecResponse(
                result=json.dumps(
                    {
                        "cancelled": False,
                        "message": "No matching active reminder found.",
                        "active_count": len(active_reminders),
                    }
                )
            )

        success = await mgr.delete_job("default", target_job.id)
        return RealtimeToolExecResponse(
            result=json.dumps(
                {
                    "cancelled": success,
                    "job_id": target_job.id,
                    "name": target_job.name,
                    "message": f"Reminder '{target_job.name}' cancelled.",
                }
            )
        )
    except Exception as exc:
        logger.exception("Failed to cancel voice reminder cron job: %s", exc)
        return RealtimeToolExecResponse(result=None, error=f"Failed to cancel reminder: {exc}")


async def _execute_list_reminders(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """List active reminders via CronManager."""
    from app.core.cron.adapters.setup import get_cron_manager
    from myrm_agent_harness.toolkits.cron.types import JobStatus, JobType

    mgr = get_cron_manager()
    try:
        jobs = await mgr.list_jobs("default")
        active_reminders = [
            {
                "id": j.id,
                "name": j.name,
                "content": j.prompt or "",
                "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
            }
            for j in jobs
            if j.status == JobStatus.ACTIVE and j.job_type == JobType.REMINDER
        ]
        return RealtimeToolExecResponse(
            result=json.dumps({"reminders": active_reminders, "count": len(active_reminders)})
        )
    except Exception as exc:
        logger.exception("Failed to list voice reminder cron jobs: %s", exc)
        return RealtimeToolExecResponse(result=None, error=f"Failed to list reminders: {exc}")


BACKGROUND_TOOL_HANDLERS: dict[str, Callable[[RealtimeToolExecRequest], Awaitable[RealtimeToolExecResponse]]] = {
    _RUN_BACKGROUND_TASK_NAME: _execute_run_background_task,
    _CANCEL_BACKGROUND_TASK_NAME: _execute_cancel_background_task,
    _GET_BACKGROUND_TASKS_STATUS_NAME: _execute_get_background_tasks_status,
    _STEER_BACKGROUND_TASK_NAME: _execute_steer_background_task,
    _SET_REMINDER_NAME: _execute_set_reminder,
    _CANCEL_REMINDER_NAME: _execute_cancel_reminder,
    _LIST_REMINDERS_NAME: _execute_list_reminders,
}
