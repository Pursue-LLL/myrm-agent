"""One-line job summary for the ``cron_manage`` list action.

[INPUT]
- core.security.redact::redact_sensitive_text (POS: 文本凭据脱敏，失败原因进入模型上下文前必须先脱敏)
- toolkits.cron.engine.parser::describe_schedule (POS: 调度的可读描述)
- toolkits.cron.types::CronJob, JobType, RunStatus, ScheduleKind (POS: cron 数据模型)

[OUTPUT]
- format_job_line: the line the model sees for one job (state, schedule, next run, last run and its failure reason)

[POS]
Text rendering for ``cron_agent_actions._do_list``; it never reads or writes the store.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.cron.engine.parser import describe_schedule
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, RunStatus, ScheduleKind

_FAILED_RUN_STATUSES = frozenset({RunStatus.ERROR, RunStatus.CIRCUIT_BREAK})
# The failure reason is redacted over a bounded prefix (a stored error can be a whole traceback) and shown shorter.
_LAST_ERROR_SCAN_CHARS = 2000
_LAST_ERROR_SHOW_CHARS = 120

_TYPE_TAGS = {JobType.SHELL: "[shell]", JobType.REMINDER: "[reminder]"}


def _schedule_tag(job: CronJob) -> str:
    """How often a recurring job runs; empty for a one-time job, whose ``next`` already says when."""
    if job.schedule.kind == ScheduleKind.ONCE:
        return ""
    return f" | {describe_schedule(job.schedule)}"


def _last_run_tag(job: CronJob) -> str:
    """When the job last ran and how it ended, with the redacted reason if that run failed.

    Empty for a job that never ran. A skipped run leaves an older ``last_error`` on the job, so the reason is
    shown only when the last run itself failed.
    """
    if job.last_run_at is None:
        return ""
    status = job.last_status.value if job.last_status else "unknown"
    tag = f" | last: {job.last_run_at.strftime('%m-%d %H:%M')} {status}"
    if job.last_status in _FAILED_RUN_STATUSES and job.last_error:
        reason = " ".join(redact_sensitive_text(job.last_error[:_LAST_ERROR_SCAN_CHARS]).split())
        if len(reason) > _LAST_ERROR_SHOW_CHARS:
            reason = reason[: _LAST_ERROR_SHOW_CHARS - 1] + "…"
        tag += f" - {reason}"
    return tag


def format_job_line(job: CronJob) -> str:
    """``> [id] name tags | state | schedule | next: … | last: … <status> - <reason>`` for one job."""
    next_run = job.next_run_at.strftime("%m-%d %H:%M") if job.next_run_at else "—"
    icon = ">" if job.status.value == "active" else "||"
    model_tag = f" ({job.model})" if job.model else ""
    fires_tag = f" [{job.fire_count}/{job.max_fires}]" if job.max_fires else ""
    ctx_tag = f" ←[{','.join(job.context_from)}]" if job.context_from else ""
    mon_tag = f" [Δ{job.monitor_config.monitor_type}]" if job.monitor_config and job.monitor_config.enabled else ""
    return (
        f"  {icon} [{job.id}] {job.name}{_TYPE_TAGS.get(job.job_type, '')}{model_tag}{fires_tag}{ctx_tag}{mon_tag}"
        f" | {job.status.value}{_schedule_tag(job)} | next: {next_run}{_last_run_tag(job)}"
    )
