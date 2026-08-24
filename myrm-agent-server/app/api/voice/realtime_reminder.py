"""Realtime voice reminder lifecycle handlers.

Short-circuit handlers for reminder tools (set_reminder, cancel_reminder, list_reminders)
invoked from OpenAI Realtime and Gemini Live voice sessions.
Directly communicates with CronManager to manage JobType.REMINDER tasks without
invoking the full Agent pipeline.

[INPUT]
- app.core.cron.adapters.setup::get_cron_manager (POS: CronManager SSOT)
- myrm_agent_harness.toolkits.cron.types::Schedule, JobType, DeliveryConfig
- app.api.voice.realtime::RealtimeToolExecRequest, RealtimeToolExecResponse

[OUTPUT]
- REMINDER_TOOL_HANDLERS: dict mapping tool names to async handler functions
- execute_set_reminder, execute_cancel_reminder, execute_list_reminders

[POS]
Voice native reminder lifecycle. Clean, single-responsibility module ensuring Cron SSOT
and sub-50ms execution latency for voice reminder actions.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from myrm_agent_harness.toolkits.cron.types import DeliveryConfig, JobType, Schedule

from app.api.voice.realtime import RealtimeToolExecRequest, RealtimeToolExecResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from myrm_agent_harness.toolkits.cron.manager import CronManager

logger = logging.getLogger(__name__)

_SET_REMINDER_NAME = "set_reminder"
_CANCEL_REMINDER_NAME = "cancel_reminder"
_LIST_REMINDERS_NAME = "list_reminders"


def _get_manager() -> CronManager:
    from app.core.cron.adapters.setup import get_cron_manager

    return get_cron_manager()


def _parse_target_run_at(arguments: dict[str, Any]) -> datetime | None:
    """Parse relative minutes or ISO timestamp into a UTC datetime."""
    now = datetime.now(UTC)

    # 1. Check relative minutes (minutes_later / minutes_from_now)
    minutes_raw = arguments.get("minutes_later") if arguments.get("minutes_later") is not None else arguments.get("minutes_from_now")
    if minutes_raw is not None:
        try:
            minutes_val = float(minutes_raw)
            if minutes_val > 0:
                return now + timedelta(minutes=minutes_val)
        except (ValueError, TypeError):
            logger.warning("Invalid minutes parameter: %r", minutes_raw)

    # 2. Check seconds from now
    seconds_raw = arguments.get("seconds_from_now")
    if seconds_raw is not None:
        try:
            seconds_val = float(seconds_raw)
            if seconds_val > 0:
                return now + timedelta(seconds=seconds_val)
        except (ValueError, TypeError):
            logger.warning("Invalid seconds_from_now: %r", seconds_raw)

    # 3. Check ISO target timestamp (schedule_time / target_time / run_at)
    target_iso = str(
        arguments.get("schedule_time", "")
        or arguments.get("target_time", "")
        or arguments.get("run_at", "")
    ).strip()
    if target_iso:
        try:
            # Handle standard ISO formats
            if target_iso.endswith("Z"):
                target_iso = target_iso[:-1] + "+00:00"
            dt_val = datetime.fromisoformat(target_iso)
            if dt_val.tzinfo is None:
                dt_val = dt_val.replace(tzinfo=UTC)
            else:
                dt_val = dt_val.astimezone(UTC)
            if dt_val > now:
                return dt_val
        except Exception as exc:
            logger.warning("Failed to parse schedule_time ISO '%s': %s", target_iso, exc)

    return None


async def execute_set_reminder(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Create a single-shot reminder cron job."""
    args = req.arguments
    title = str(
        args.get("content", "")
        or args.get("title", "")
        or args.get("prompt", "")
        or args.get("task", "")
    ).strip()
    if not title:
        return RealtimeToolExecResponse(result=None, error="content is required")

    run_at = _parse_target_run_at(args)
    if run_at is None:
        return RealtimeToolExecResponse(
            result=None,
            error="Please specify when to remind (e.g. minutes_later: 10 or a valid future schedule_time)",
        )

    mgr = _get_manager()
    user_id = "default"
    chat_id = req.chat_id or "realtime-voice"
    schedule = Schedule.once(run_at=run_at)

    try:
        job = await mgr.create_job(
            user_id=user_id,
            name=title[:80],
            job_type=JobType.REMINDER,
            schedule=schedule,
            prompt=title,
            chat_id=chat_id,
            agent_id=req.agent_id,
            delivery=DeliveryConfig(channel="chat", target=chat_id),
            delete_after_run=False,
        )
        time_str = run_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted_delta = f"{int((run_at - datetime.now(UTC)).total_seconds() // 60)} minutes"
        logger.info("Voice reminder created: job_id=%s title=%s at=%s", job.id, title, time_str)
        return RealtimeToolExecResponse(
            result=json.dumps(
                {
                    "success": True,
                    "job_id": job.id,
                    "name": job.name,
                    "title": job.name,
                    "time": time_str,
                    "remind_in": formatted_delta,
                    "message": f"Reminder set for '{job.name}' in {formatted_delta} ({time_str}).",
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        logger.exception("Failed to create voice reminder: %s", exc)
        return RealtimeToolExecResponse(result=None, error=f"Failed to create reminder: {exc}")


async def execute_cancel_reminder(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """Cancel a reminder by reminder_id or fuzzy match content/title."""
    args = req.arguments
    job_id = str(args.get("reminder_id", "") or args.get("job_id", "")).strip()
    query = str(args.get("content", "") or args.get("title", "") or args.get("query", "")).strip().lower()
    cancel_latest = bool(args.get("cancel_latest", False))

    mgr = _get_manager()
    user_id = "default"

    # 1. Direct cancel by job_id if provided
    if job_id:
        try:
            job = await mgr.get_job(job_id)
            if job and job.user_id == user_id:
                await mgr.delete_job(job_id)
                logger.info("Voice reminder deleted by id: %s", job_id)
                return RealtimeToolExecResponse(
                    result=json.dumps(
                        {"cancelled": True, "job_id": job_id, "title": job.name},
                        ensure_ascii=False,
                    )
                )
        except Exception as exc:
            logger.warning("Failed to delete reminder by job_id %s: %s", job_id, exc)

    # 2. Match by title query across active reminder jobs
    try:
        jobs = await mgr.list_jobs(user_id)
        reminder_jobs = [j for j in jobs if j.job_type == JobType.REMINDER and j.status.value == "active"]

        matched_job = None
        if query:
            for j in reminder_jobs:
                if query in j.name.lower() or (j.prompt and query in j.prompt.lower()):
                    matched_job = j
                    break
        elif cancel_latest or reminder_jobs:
            # If cancel_latest or no specific query given, cancel the soonest active reminder
            reminder_jobs.sort(key=lambda x: x.next_run_at or datetime.max.replace(tzinfo=UTC))
            matched_job = reminder_jobs[0]

        if matched_job:
            await mgr.delete_job(matched_job.id)
            logger.info("Voice reminder deleted: %s (%s)", matched_job.name, matched_job.id)
            return RealtimeToolExecResponse(
                result=json.dumps(
                    {
                        "cancelled": True,
                        "job_id": matched_job.id,
                        "name": matched_job.name,
                        "title": matched_job.name,
                        "message": f"Cancelled reminder: '{matched_job.name}'.",
                    },
                    ensure_ascii=False,
                )
            )

        return RealtimeToolExecResponse(
            result=json.dumps(
                {
                    "cancelled": False,
                    "message": "No matching active reminder found.",
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        logger.exception("Failed to cancel voice reminder: %s", exc)
        return RealtimeToolExecResponse(result=None, error=f"Failed to cancel reminder: {exc}")


async def execute_list_reminders(req: RealtimeToolExecRequest) -> RealtimeToolExecResponse:
    """List all upcoming/active reminders."""
    mgr = _get_manager()
    user_id = "default"
    try:
        jobs = await mgr.list_jobs(user_id)
        now = datetime.now(UTC)
        reminders = []
        for j in jobs:
            if j.job_type == JobType.REMINDER and j.status.value == "active":
                next_str = j.next_run_at.strftime("%Y-%m-%d %H:%M UTC") if j.next_run_at else "soon"
                remind_in = (
                    f"{int((j.next_run_at - now).total_seconds() // 60)} min" if j.next_run_at and j.next_run_at > now else "now"
                )
                reminders.append(
                    {
                        "id": j.id,
                        "job_id": j.id,
                        "name": j.name,
                        "title": j.name,
                        "content": j.prompt or j.name,
                        "next_run_at": next_str,
                        "remind_in": remind_in,
                    }
                )

        return RealtimeToolExecResponse(
            result=json.dumps(
                {
                    "reminders": reminders,
                    "count": len(reminders),
                    "message": f"You have {len(reminders)} active reminder(s)." if reminders else "No active reminders.",
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        logger.exception("Failed to list voice reminders: %s", exc)
        return RealtimeToolExecResponse(result=None, error=f"Failed to list reminders: {exc}")


REMINDER_TOOL_HANDLERS: dict[
    str,
    Callable[[RealtimeToolExecRequest], Awaitable[RealtimeToolExecResponse]],
] = {
    _SET_REMINDER_NAME: execute_set_reminder,
    _CANCEL_REMINDER_NAME: execute_cancel_reminder,
    _LIST_REMINDERS_NAME: execute_list_reminders,
}
