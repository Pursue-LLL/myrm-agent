"""Action implementations for the ``cron_manage`` tool.

One coroutine per ``action`` value (add, list, update, remove, run, pause, resume,
blueprints). Each takes the already-resolved tool arguments, calls ``CronManager`` and
returns the text (or JSON) the model sees; failures come back as plain messages.

[INPUT]
- toolkits.cron.blueprint_job_spec::DEFAULT_JOB_TIMEOUT_SECONDS, BlueprintJobSpec (POS: blueprint 产出的完整 job 定义)
- toolkits.cron.cron_agent_params::_MIN_INTERVAL_MINUTES, _MIN_INTERVAL_MS, _build_active_hours, _build_monitor_config, _build_schedule, _build_trigger_config, _parse_context_from, _parse_expires_after, _parse_session_mode (POS: cron_manage_tool 参数解析与校验)
- toolkits.cron.engine.name_generator::generate_job_name (POS: 任务名生成)
- toolkits.cron.engine.parser::describe_schedule (POS: cron 表达式解析与下次运行时间计算)
- toolkits.cron.manager::CronManager (POS: cron CRUD 编排层)
- toolkits.cron.types::CronJobPatch, DeliveryConfig, JobType, Schedule, ScheduleKind, SessionTarget (POS: cron 数据模型)

[OUTPUT]
- BlueprintCatalogProvider / DeliveryResolver: callables the tool factory injects into the actions
- _do_add / _do_list / _do_update / _do_remove / _do_run / _do_pause / _do_resume / _do_blueprints:
  one ``cron_manage`` action each, returning the text the model sees

[POS]
Action half of the ``cron_manage`` tool: validates what the model asked for, calls
``CronManager`` and formats the result. ``cron_agent_tools.py`` only dispatches to it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.blueprint_job_spec import (
    DEFAULT_JOB_TIMEOUT_SECONDS,
    BlueprintJobSpec,
)
from myrm_agent_harness.toolkits.cron.cron_agent_params import (
    _MIN_INTERVAL_MINUTES,
    _MIN_INTERVAL_MS,
    _build_active_hours,
    _build_monitor_config,
    _build_schedule,
    _build_trigger_config,
    _parse_context_from,
    _parse_expires_after,
    _parse_session_mode,
)
from myrm_agent_harness.toolkits.cron.engine.name_generator import generate_job_name
from myrm_agent_harness.toolkits.cron.engine.parser import describe_schedule
from myrm_agent_harness.toolkits.cron.types import (
    CronJobPatch,
    DeliveryConfig,
    JobType,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.manager import CronManager

BlueprintCatalogProvider = Callable[[], str]
DeliveryResolver = Callable[[str], DeliveryConfig]


async def _do_blueprints(provider: BlueprintCatalogProvider | None) -> str:
    if provider is None:
        return "Blueprint catalog is not available in this session."
    return provider()


async def _do_add(
    mgr: CronManager,
    user_id: str,
    prompt: str,
    command: str,
    model: str,
    cron_expr: str,
    every_minutes: int,
    at: str,
    tz: str,
    name: str,
    webhook_url: str,
    failure_webhook_url: str,
    recurring_confirmed: bool,
    active_start: str,
    active_end: str,
    active_tz: str,
    chat_id: str | None = None,
    max_fires: int = 0,
    expires_after: str = "",
    agent_id: str | None = None,
    context_from: str = "",
    monitor_type: str = "",
    monitor_enabled: bool = False,
    session_mode: str = "",
    stream_url: str = "",
    stream_protocol: str = "",
    stream_filter_json_path: str = "",
    stream_filter_regex: str = "",
    stream_headers: str = "",
    poll_url: str = "",
    poll_json_path: str = "",
    poll_interval_seconds: int = 0,
    reminder: bool = False,
    required_capabilities: tuple[str, ...] = (),
    tools_allowed: tuple[str, ...] | None = None,
    skill_ids: tuple[str, ...] = (),
    *,
    spec: BlueprintJobSpec | None,
    resolve_delivery: DeliveryResolver,
) -> str:
    has_prompt = bool(prompt.strip())
    has_command = bool(command.strip())

    if reminder and has_command:
        return "Reminder tasks use prompt only — do not set command."
    if reminder and not has_prompt:
        return "Reminder tasks require a non-empty prompt."

    if has_prompt and has_command:
        return "Provide either prompt (agent task) or command (shell task), not both."
    if spec is None and not reminder and not has_prompt and not has_command:
        return "Either prompt or command is required."

    has_stream_or_poll = bool(stream_url.strip()) or bool(poll_url.strip())
    has_schedule = spec is not None or any([cron_expr, every_minutes > 0, at])

    if not has_schedule and not has_stream_or_poll:
        return "Provide a schedule (cron_expr/every_minutes/at) or a trigger (stream_url/poll_url)."

    schedule: Schedule | None = None
    if has_schedule:
        if spec and (every_minutes > 0 or at):
            return "A blueprint sets its own schedule; do not pass every_minutes or at with it."
        err, schedule = (None, spec.schedule) if spec else _build_schedule(cron_expr, every_minutes, at, tz)
        if err or not schedule:
            return err or "Schedule build failed."
        if spec and schedule.kind == ScheduleKind.INTERVAL and (schedule.interval_ms or 0) < _MIN_INTERVAL_MS:
            return f"A blueprint interval must be at least {_MIN_INTERVAL_MINUTES} minutes."

        is_recurring = schedule.kind in (ScheduleKind.CRON, ScheduleKind.INTERVAL)
        if is_recurring and not recurring_confirmed:
            return (
                "Recurring schedules (cron_expr, every_minutes or a blueprint) require "
                "recurring_confirmed=true to prevent accidental creation. "
                "For a one-time reminder without a blueprint, use 'at' instead."
            )

    if not has_schedule and has_stream_or_poll:
        schedule = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=_MIN_INTERVAL_MS)

    if schedule is None:
        return "Schedule build failed."

    trig_err, trigger_config = _build_trigger_config(
        stream_url,
        stream_protocol,
        stream_filter_json_path,
        stream_filter_regex,
        stream_headers,
        poll_url,
        poll_json_path,
        poll_interval_seconds,
    )
    if trig_err:
        return trig_err

    if has_command:
        job_type = JobType.SHELL
        task_name = name.strip() or generate_job_name(command.strip())
    elif reminder:
        job_type = JobType.REMINDER
        task_name = name.strip() or generate_job_name(prompt.strip())
    else:
        job_type = spec.job_type if spec else JobType.AGENT
        task_name = name.strip() or generate_job_name(prompt.strip())

    delivery = resolve_delivery(webhook_url)
    failure_delivery = resolve_delivery(failure_webhook_url) if failure_webhook_url.strip() else None
    active_hours = _build_active_hours(active_start, active_end, active_tz)

    effective_max_fires: int | None = max_fires if max_fires > 0 else None
    try:
        expires_at = _parse_expires_after(expires_after)
    except (ValueError, TypeError):
        return f"Invalid expires_after format: '{expires_after}'. Use '3d', '2w', '3m', or ISO 8601."

    parsed_context_from = _parse_context_from(context_from)
    mon_err, monitor_config, monitor_off = _build_monitor_config(monitor_type, monitor_enabled)
    if mon_err:
        return mon_err
    if spec and monitor_config is None and not monitor_off:
        monitor_config = spec.monitor_config

    sm_err, session_target = _parse_session_mode(session_mode, spec.session_target if spec else SessionTarget.ISOLATED)
    if sm_err:
        return sm_err

    try:
        job = await mgr.create_job(
            user_id=user_id,
            name=task_name,
            job_type=job_type,
            schedule=schedule,
            prompt=prompt.strip() or None,
            command=command.strip() or (spec.command if spec else None),
            model=model.strip() or None,
            chat_id=chat_id,
            agent_id=agent_id,
            delivery=delivery,
            failure_delivery=failure_delivery,
            active_hours=active_hours,
            session_target=session_target,
            deduplicate=spec.deduplicate if spec else False,
            skip_if_active=spec.skip_if_active if spec else False,
            timeout_seconds=(spec.timeout_seconds if spec else None) or DEFAULT_JOB_TIMEOUT_SECONDS,
            max_fires=effective_max_fires,
            expires_at=expires_at,
            context_from=parsed_context_from,
            monitor_config=monitor_config,
            failure_alert=spec.failure_alert if spec else None,
            pre_condition_script=spec.pre_condition_script if spec else None,
            triggers=trigger_config,
            required_capabilities=required_capabilities,
            tools_allowed=tools_allowed,
            skill_ids=skill_ids,
        )
    except ValueError as exc:
        return str(exc)

    next_run = job.next_run_at.strftime("%Y-%m-%d %H:%M UTC") if job.next_run_at else "N/A"
    type_label = {
        JobType.SHELL: "Shell",
        JobType.REMINDER: "Reminder",
        JobType.ROUTER: "Router",
    }.get(job_type, "Agent")

    result: dict[str, str | int | list[str] | None] = {
        "status": "success",
        "action": "add",
        "job_id": job.id,
        "name": job.name,
        "job_type": type_label,
        "model": job.model,
        "schedule": describe_schedule(schedule),
        "next_run": next_run,
    }
    if job.max_fires is not None:
        result["max_fires"] = job.max_fires
    if job.expires_at is not None:
        result["expires_at"] = job.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    if job.context_from:
        result["context_from"] = list(job.context_from)
    if job.monitor_config and job.monitor_config.enabled:
        result["monitor"] = job.monitor_config.monitor_type
    if trigger_config:
        if trigger_config.streams:
            result["stream"] = trigger_config.streams[0].url
        if trigger_config.polls:
            result["poll"] = trigger_config.polls[0].url

    return json.dumps(result, ensure_ascii=False)


async def _do_list(mgr: CronManager, user_id: str, name_filter: str) -> str:
    jobs = await mgr.list_jobs(user_id, name_filter=name_filter.strip() or None)
    if not jobs:
        return "No scheduled tasks."

    lines: list[str] = [f"{len(jobs)} task(s):\n"]
    for j in jobs:
        next_run = j.next_run_at.strftime("%m-%d %H:%M") if j.next_run_at else "—"
        icon = ">" if j.status.value == "active" else "||"
        type_tag = {
            JobType.SHELL: "[shell]",
            JobType.REMINDER: "[reminder]",
        }.get(j.job_type, "")
        model_tag = f" ({j.model})" if j.model else ""
        fires_tag = f" [{j.fire_count}/{j.max_fires}]" if j.max_fires else ""
        ctx_tag = f" ←[{','.join(j.context_from)}]" if j.context_from else ""
        mon_tag = f" [Δ{j.monitor_config.monitor_type}]" if j.monitor_config and j.monitor_config.enabled else ""
        lines.append(
            f"  {icon} [{j.id}] {j.name}{type_tag}{model_tag}{fires_tag}{ctx_tag}{mon_tag} | {j.status.value} | next: {next_run}"
        )
    return "\n".join(lines)


async def _do_update(
    mgr: CronManager,
    user_id: str,
    job_id: str,
    prompt: str,
    command: str,
    model: str,
    cron_expr: str,
    every_minutes: int,
    at: str,
    tz: str,
    name: str,
    max_fires: int = 0,
    expires_after: str = "",
    context_from: str = "",
    monitor_type: str = "",
    monitor_enabled: bool = False,
    session_mode: str = "",
    required_capabilities: tuple[str, ...] | None = None,
    tools_allowed: tuple[str, ...] | None = None,
    skill_ids: tuple[str, ...] | None = None,
) -> str:
    if not job_id:
        return "job_id required. Use action='list' first."

    new_schedule: Schedule | None = None
    if any([cron_expr, every_minutes > 0, at]):
        err, new_schedule = _build_schedule(cron_expr, every_minutes, at, tz)
        if err:
            return err

    effective_max_fires: int | None = max_fires if max_fires > 0 else None
    try:
        expires_at = _parse_expires_after(expires_after)
    except (ValueError, TypeError):
        return f"Invalid expires_after format: '{expires_after}'. Use '3d', '2w', '3m', or ISO 8601."

    parsed_context_from = _parse_context_from(context_from) if context_from.strip() else None
    mon_err, monitor_config, clear_monitor = _build_monitor_config(monitor_type, monitor_enabled)
    if mon_err:
        return mon_err

    parsed_session_target: SessionTarget | None = None
    if session_mode.strip():
        sm_err, parsed_session_target = _parse_session_mode(session_mode)
        if sm_err:
            return sm_err

    patch = CronJobPatch(
        name=name.strip() or None,
        prompt=prompt.strip() or None,
        command=command.strip() or None,
        model=model.strip() or None,
        schedule=new_schedule,
        max_fires=effective_max_fires,
        expires_at=expires_at,
        context_from=parsed_context_from,
        monitor_config=monitor_config,
        clear_monitor_config=clear_monitor,
        session_target=parsed_session_target,
        required_capabilities=required_capabilities,
        tools_allowed=tools_allowed,
        skill_ids=skill_ids,
        clear_skill_ids=skill_ids is not None and len(skill_ids) == 0,
    )

    try:
        job = await mgr.update_job(job_id, user_id, patch)
    except ValueError as exc:
        return str(exc)

    if not job:
        return f"Task {job_id} not found."

    next_run = job.next_run_at.strftime("%Y-%m-%d %H:%M UTC") if job.next_run_at else "N/A"
    type_label = {
        JobType.SHELL: "Shell",
        JobType.REMINDER: "Reminder",
    }.get(job.job_type, "Agent")

    result: dict[str, str | int | list[str] | None] = {
        "status": "success",
        "action": "update",
        "job_id": job.id,
        "name": job.name,
        "job_type": type_label,
        "model": job.model,
        "schedule": describe_schedule(job.schedule),
        "next_run": next_run,
    }
    if job.max_fires is not None:
        result["max_fires"] = job.max_fires
        result["fire_count"] = job.fire_count
    if job.expires_at is not None:
        result["expires_at"] = job.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    if job.context_from:
        result["context_from"] = list(job.context_from)
    if job.monitor_config and job.monitor_config.enabled:
        result["monitor"] = job.monitor_config.monitor_type

    return json.dumps(result, ensure_ascii=False)


async def _do_remove(mgr: CronManager, user_id: str, job_id: str) -> str:
    if not job_id:
        return "job_id required. Use action='list' to find IDs."
    deleted = await mgr.delete_job(job_id, user_id)
    return f"Task {job_id} deleted." if deleted else f"Task {job_id} not found."


async def _do_run(mgr: CronManager, user_id: str, job_id: str) -> str:
    if not job_id:
        return "job_id required. Use action='list' to find IDs."
    triggered = await mgr.trigger_now(job_id, user_id)
    return f"Task {job_id} triggered." if triggered else f"Task {job_id} not found or not active."


async def _do_pause(mgr: CronManager, user_id: str, job_id: str) -> str:
    if not job_id:
        return "job_id required. Use action='list' to find IDs."
    job = await mgr.pause_job(job_id, user_id)
    if not job:
        return f"Task {job_id} not found."
    return json.dumps(
        {"status": "success", "action": "pause", "job_id": job.id, "name": job.name},
        ensure_ascii=False,
    )


async def _do_resume(mgr: CronManager, user_id: str, job_id: str) -> str:
    if not job_id:
        return "job_id required. Use action='list' to find IDs."
    try:
        job = await mgr.resume_job(job_id, user_id)
    except ValueError:
        return f"Cannot resume task {job_id}"
    if not job:
        return f"Task {job_id} not found."
    next_run = job.next_run_at.strftime("%Y-%m-%d %H:%M UTC") if job.next_run_at else "N/A"
    return json.dumps(
        {"status": "success", "action": "resume", "job_id": job.id, "name": job.name, "next_run": next_run},
        ensure_ascii=False,
    )
