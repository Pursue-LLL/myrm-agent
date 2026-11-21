"""Cron job validation and normalization helpers.

The field-level rules that reject a job live together here, apart from the CRUD
orchestration's persistence ordering and scheduler notification, so they can be read
(and tested) on their own.

[INPUT]
- cron.engine.helpers::is_within_active_hours, next_eligible_run (POS: pure engine helpers: the active window and the next slot to book)
- cron.engine.parser::compute_next_run, validate_cron_expr, validate_timezone (POS: 下一次触发时刻、cron 表达式与时区校验)
- cron.triggers::TriggerConfig, WebhookTrigger, generate_webhook_path, generate_webhook_secret (POS: webhook 触发定义与凭据生成)
- cron.types::CronJob, CronJobPatch, JobType, Schedule, ScheduleKind, SYSTEM_JOB_NAME_PREFIX, is_system_job_name (POS: cron 数据模型)

[OUTPUT]
- CronValidationMixin: _validate_create / _validate_name / _validate_rename / _validate_job_content /
  _validate_update_content / _validate_schedule / _validate_context_from / _validate_resume_preconditions /
  _book_slot / _ensure_webhook_credentials / _resolve_name_conflict

[POS]
Validation half of the cron CRUD manager. A mixin rather than free functions because every
rule either needs the job store (reference and name checks) or the shell-enabled policy, both
of which belong to the manager instance. ``_book_slot`` is the one booking a user's input makes
(create, edit, resume): the next slot, or a refusal when the job's active window is one its
schedule never reaches. ``_validate_name`` and ``_validate_rename`` keep the reserved names (the
``__`` prefix) for the application's own jobs: a system job takes one and no other job does, and no
rename moves a job into or out of that set.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import is_within_active_hours, next_eligible_run
from myrm_agent_harness.toolkits.cron.engine.parser import (
    compute_next_run,
    validate_cron_expr,
    validate_timezone,
)
from myrm_agent_harness.toolkits.cron.triggers import (
    TriggerConfig,
    WebhookTrigger,
    generate_webhook_path,
    generate_webhook_secret,
)
from myrm_agent_harness.toolkits.cron.types import (
    SYSTEM_JOB_NAME_PREFIX,
    JobStatus,
    JobType,
    ScheduleKind,
    is_system_job_name,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore
    from myrm_agent_harness.toolkits.cron.types import CronJob, CronJobPatch, Schedule

# ``next_eligible_run`` ends on a slot outside the active window when no candidate within its budget lies inside it.
# That proves the window unreachable only if the budget covered a whole daily cycle: a schedule that fires every few
# seconds spends it within hours, and for it the dispatch guards keep skipping and rebooking.
_UNREACHABLE_WINDOW_SPAN = timedelta(days=1)

_RESERVED_NAME_MESSAGE = (
    f"names starting with {SYSTEM_JOB_NAME_PREFIX!r} are reserved for the application's own jobs; choose another name"
)


def _once_has_passed(schedule: Schedule, now: datetime) -> bool:
    """A one-shot names its own instant; ``compute_next_run`` yields nothing once that instant is not ahead of ``now``."""
    return schedule.kind == ScheduleKind.ONCE and compute_next_run(schedule, now) is None


class CronValidationMixin:
    """Field-level validation for cron job creation, updates, and resumption."""

    if TYPE_CHECKING:
        # Provided by the concrete manager that composes this mixin.
        _store: CronStore
        _shell_enabled: bool

    @staticmethod
    def _validate_resume_preconditions(job: CronJob, now: datetime) -> None:
        """Reject resuming a job whose constraints make it immediately un-runnable."""
        if job.status == JobStatus.COMPLETED:
            raise ValueError("completed jobs cannot be resumed")
        if _once_has_passed(job.schedule, now):
            raise ValueError("its scheduled time has passed; set a new time before resuming")
        if job.expires_at is not None:
            expires_at = job.expires_at if job.expires_at.tzinfo else job.expires_at.replace(tzinfo=UTC)
            if now >= expires_at:
                raise ValueError("job has expired; extend expires_at before resuming")
        if job.max_fires is not None and job.fire_count >= job.max_fires:
            raise ValueError("max execution count reached; increase max_fires before resuming")

    @staticmethod
    def _book_slot(job: CronJob, now: datetime) -> datetime | None:
        """The slot a create, an edit or a resume books for ``job``; a window its schedule never reaches is refused.

        Without the refusal the job would stay enabled with a next run years away (the slot scan ends on a far slot
        outside the window) and never run. A one-shot names its own instant, which the active window does not restrict.
        """
        slot = next_eligible_run(job, now)
        if (
            slot is not None
            and job.schedule.kind != ScheduleKind.ONCE
            and not is_within_active_hours(job.active_hours, now=slot)
            and slot - now >= _UNREACHABLE_WINDOW_SPAN
        ):
            raise ValueError(
                "no run of this schedule falls inside its active hours; widen the hours or change the schedule"
            )
        return slot

    @staticmethod
    def _validate_name(name: str, *, system: bool) -> None:
        """A reserved name belongs to the application's own jobs, and a system job takes no other name.

        The second direction closes a loophole: a job flagged as a system job under a name the listings show would
        escape the plan's job quota, which counts only the user's jobs.
        """
        reserved = is_system_job_name(name)
        if reserved and not system:
            raise ValueError(_RESERVED_NAME_MESSAGE)
        if system and not reserved:
            raise ValueError(f"a system job's name must start with {SYSTEM_JOB_NAME_PREFIX!r}")

    @staticmethod
    def _validate_rename(current: str, new: str) -> None:
        """No rename moves a job into or out of the reserved names."""
        if new != current and (is_system_job_name(new) or is_system_job_name(current)):
            raise ValueError(_RESERVED_NAME_MESSAGE)

    def _validate_create(
        self,
        job_type: JobType,
        schedule: Schedule,
        prompt: str | None,
        command: str | None,
        pre_condition_script: str | None = None,
    ) -> None:
        """Validate required fields by job type before persisting."""
        if job_type == JobType.SHELL and not self._shell_enabled:
            raise ValueError("shell jobs are not enabled")
        self._validate_job_content(job_type, prompt, command, pre_condition_script)
        self._validate_schedule(schedule)

    @staticmethod
    def _validate_job_content(
        job_type: JobType,
        prompt: str | None,
        command: str | None,
        pre_condition_script: str | None,
    ) -> None:
        """Require what the job's runner executes.

        A shell job needs a command. A router job passes its input straight through, so a
        pre-condition script can stand in for the prompt. Every other type needs a prompt.
        """
        if job_type == JobType.SHELL:
            if not command:
                raise ValueError("SHELL job requires a non-empty 'command'")
        elif job_type == JobType.ROUTER:
            if not (prompt or pre_condition_script):
                raise ValueError("ROUTER job requires a non-empty 'prompt' or 'pre_condition_script'")
        elif not prompt:
            raise ValueError(f"{job_type.value.upper()} job requires a non-empty 'prompt'")

    @classmethod
    def _validate_update_content(cls, job: CronJob, patch: CronJobPatch) -> None:
        """Apply the creation content rule to the record a patch would produce.

        Checked only when the patch touches a field the rule reads, so stored jobs stay
        editable through every other field.
        """
        if (
            patch.prompt is None
            and patch.command is None
            and patch.pre_condition_script is None
            and not patch.clear_pre_condition_script
        ):
            return
        script = job.pre_condition_script if patch.pre_condition_script is None else patch.pre_condition_script
        cls._validate_job_content(
            job.job_type,
            job.prompt if patch.prompt is None else patch.prompt,
            job.command if patch.command is None else patch.command,
            None if patch.clear_pre_condition_script else script,
        )

    @staticmethod
    def _validate_schedule(schedule: Schedule) -> None:
        """Validate the cron expression and the timezone, and that a one-shot's time is still ahead."""
        if schedule.kind == ScheduleKind.CRON and not validate_cron_expr(schedule.expr or ""):
            raise ValueError(f"invalid cron expression: {schedule.expr!r}")
        if schedule.tz and not validate_timezone(schedule.tz):
            raise ValueError(f"unknown timezone: {schedule.tz!r}")
        if _once_has_passed(schedule, datetime.now(UTC)):
            raise ValueError("its scheduled time has passed; choose a future time")

    async def _validate_context_from(self, job_id: str, context_from: tuple[str, ...]) -> None:
        """Ensure context_from references are valid and non-circular."""
        for ref_id in context_from:
            if ref_id == job_id:
                raise ValueError(f"context_from must not reference the job itself: {ref_id!r}")
            ref_job = await self._store.get_job(ref_id)
            if ref_job is None:
                raise ValueError(f"context_from references non-existent job: {ref_id!r}")

    @staticmethod
    def _ensure_webhook_credentials(triggers: TriggerConfig) -> TriggerConfig:
        """Fill in missing path/secret for each webhook trigger."""
        if not triggers.webhooks:
            return triggers
        patched = tuple(
            WebhookTrigger(
                path=wh.path or generate_webhook_path(),
                secret=wh.secret or generate_webhook_secret(),
            )
            for wh in triggers.webhooks
        )
        return TriggerConfig(
            webhooks=patched,
            events=triggers.events,
            system_events=triggers.system_events,
            polls=triggers.polls,
            streams=triggers.streams,
        )

    async def _resolve_name_conflict(self, name: str) -> str:
        """Auto-append (2), (3), etc. if a job with this name already exists.

        Args:
            name: Desired task name

        Returns:
            Unique name (original or with suffix like " (2)")
        """
        # Query store directly to avoid mock issues in tests
        existing_jobs = await self._store.list_jobs()
        existing_names = {job.name for job in existing_jobs}

        if name not in existing_names:
            return name

        # Find next available suffix: (2), (3), ...
        suffix = 2
        while f"{name} ({suffix})" in existing_names:
            suffix += 1

        return f"{name} ({suffix})"
