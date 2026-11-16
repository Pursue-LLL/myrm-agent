"""JSON the ``cron_manage`` tool hands back after it adds, updates or resumes a task.

[INPUT]
- toolkits.cron.cron_agent_timezone::zone_fields (POS: cron_manage_tool 的时区契约)
- toolkits.cron.engine.parser::describe_schedule (POS: cron 表达式解析与下次运行时间计算)
- toolkits.cron.types::CronJob, JobType (POS: cron 数据模型)

[OUTPUT]
- job_result: the JSON of an added or updated task
- resume_result: the JSON of a resumed task

[POS]
Result half of the ``cron_manage`` tool. One place decides what the model reads back about a task and when it runs
next, in UTC and on the clock of the zone its times were read in, so add, update and resume cannot drift apart.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.cron.cron_agent_timezone import zone_fields
from myrm_agent_harness.toolkits.cron.engine.parser import describe_schedule
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType

_TYPE_LABELS = {JobType.SHELL: "Shell", JobType.REMINDER: "Reminder", JobType.ROUTER: "Router"}

JsonValue = str | int | list[str] | None


def _utc_text(moment: datetime) -> str:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _next_run_fields(job: CronJob, zone: str | None) -> dict[str, JsonValue]:
    """``next_run`` in UTC, then ``zone`` and the same instant on that zone's clock."""
    fields: dict[str, JsonValue] = {"next_run": _utc_text(job.next_run_at) if job.next_run_at else "N/A"}
    fields.update(zone_fields(zone, job.next_run_at))
    return fields


def job_result(action: str, job: CronJob, zone: str | None) -> str:
    """The JSON of a task that was just added or updated; ``zone`` is the zone its times were read in (None is UTC)."""
    result: dict[str, JsonValue] = {
        "status": "success",
        "action": action,
        "job_id": job.id,
        "name": job.name,
        "job_type": _TYPE_LABELS.get(job.job_type, "Agent"),
        "model": job.model,
        "schedule": describe_schedule(job.schedule),
        **_next_run_fields(job, zone),
    }
    if job.max_fires is not None:
        result["max_fires"] = job.max_fires
        result["fire_count"] = job.fire_count
    if job.expires_at is not None:
        result["expires_at"] = _utc_text(job.expires_at)
    if job.context_from:
        result["context_from"] = list(job.context_from)
    if job.monitor_config and job.monitor_config.enabled:
        result["monitor"] = job.monitor_config.monitor_type
    if job.triggers:
        if job.triggers.streams:
            result["stream"] = job.triggers.streams[0].url
        if job.triggers.polls:
            result["poll"] = job.triggers.polls[0].url
    return json.dumps(result, ensure_ascii=False)


def resume_result(job: CronJob) -> str:
    """The JSON of a task that was just resumed, on the clock of its own zone."""
    result: dict[str, JsonValue] = {
        "status": "success",
        "action": "resume",
        "job_id": job.id,
        "name": job.name,
        **_next_run_fields(job, job.schedule.tz),
    }
    return json.dumps(result, ensure_ascii=False)
