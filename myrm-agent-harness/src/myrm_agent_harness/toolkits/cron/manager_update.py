"""Update path of the cron CRUD manager.

[INPUT]
- infra.incremental.types::ResetReason (POS: Domain types for incremental monitoring.)
- cron.engine.scheduler::CronScheduler (POS: timer-based scheduling engine)
- cron.manager_validation::CronValidationMixin (POS: validation half of the cron CRUD manager and the one booking a user's input makes)
- cron.types::CronJob, CronJobPatch, JobStatus (POS: cron data models)

[OUTPUT]
- CronUpdateMixin: ``update_job`` (patch application), ``_activate`` (the shared resume path) and the monitor-baseline
  reset a content change triggers

[POS]
Update half of the cron CRUD manager, mixed into ``CronManager``. Applies a ``CronJobPatch`` to the stored job
once the content rules pass; a status patch to active on a job that is not enabled is a resume (preconditions,
failure count, last error and pause reason reset, next slot booked), any other status patch is a person's own
decision and drops the scheduler's pause reason, and an enabled job whose schedule, cooldown or active window changes
gets its slot booked again (a one-shot's slot moves only with its schedule). Resets an enabled monitor's baseline when its
command, prompt or monitor type changes, persists the job and notifies the scheduler.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.manager_validation import CronValidationMixin
from myrm_agent_harness.toolkits.cron.types import JobStatus, ScheduleKind

if TYPE_CHECKING:
    from myrm_agent_harness.infra.incremental.types import ResetReason
    from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
    from myrm_agent_harness.toolkits.cron.types import CronJob, CronJobPatch

logger = logging.getLogger(__name__)


def _moves_slot(job: CronJob, patch: CronJobPatch) -> bool:
    """Whether the patch changes an input of ``next_eligible_run`` for this job.

    A one-shot names its own instant, so only a new schedule moves it; the active window and the cooldown move the
    slot of every other kind. Recomputing a due one-shot's slot would clear it and leave an enabled job with none.
    """
    if patch.schedule is not None:
        return True
    edits_window_or_cooldown = (
        patch.active_hours is not None or patch.clear_active_hours or patch.cooldown_seconds is not None
    )
    return edits_window_or_cooldown and job.schedule.kind != ScheduleKind.ONCE


class CronUpdateMixin(CronValidationMixin):
    """Patch application for ``CronManager``; the rules it applies come from ``CronValidationMixin``."""

    if TYPE_CHECKING:
        # Provided by the concrete manager that composes this mixin (``_store`` is declared by the validation mixin).
        _scheduler: CronScheduler

    def _activate(self, job: CronJob, now: datetime) -> None:
        """Re-enable a job: the one path a resume and a status patch to active share.

        The preconditions are checked on the job as the patch leaves it, so an edit that removes the obstacle (a new
        time, a later expiry) and the activation can arrive together. The failure story restarts (count, last error
        and the reason the scheduler paused the job) and the next slot is booked from now, because a paused job holds
        no valid slot.
        """
        self._validate_resume_preconditions(job, now)
        job.status = JobStatus.ACTIVE
        job.consecutive_failures = 0
        job.last_error = None
        job.paused_reason = None
        job.next_run_at = self._book_slot(job, now)

    async def _reset_baseline_on_change(self, job_id: str, reset_reason: ResetReason) -> None:
        """Reset monitor baseline and record reason.

        Called when command/prompt/monitor_type changes with enabled monitoring.
        Clears baseline data and persists reset metadata for user visibility.

        Args:
            job_id: Job identifier.
            reset_reason: Why the baseline was reset.
        """
        state = await self._store.get_monitor_state(job_id)
        if state:
            state.data = {}
            state.last_reset_at = datetime.now(UTC)
            state.last_reset_reason = reset_reason
            await self._store.save_monitor_state(state)
        else:
            await self._store.delete_monitor_state(job_id)
        logger.info(
            "Auto-reset monitor baseline due to %s change: %s",
            reset_reason.replace("_", "/"),
            job_id,
        )

    async def update_job(self, job_id: str, patch: CronJobPatch) -> CronJob | None:
        """Update job fields via patch.

        Auto-resets monitor baseline when command/prompt/monitor_type changes
        with enabled monitor.
        """
        job = await self._store.get_job(job_id)
        if not job:
            return None
        self._validate_update_content(job, patch)

        now = datetime.now(UTC)
        reset_reason: ResetReason | None = None
        activating = patch.status == JobStatus.ACTIVE and job.status != JobStatus.ACTIVE

        if patch.name is not None:
            self._validate_rename(job.name, patch.name)
            job.name = patch.name
        if patch.status is not None and not activating:
            job.status = patch.status
            job.paused_reason = None
        if patch.schedule is not None:
            self._validate_schedule(patch.schedule)
            job.schedule = patch.schedule
        if patch.prompt is not None and patch.prompt != job.prompt:
            job.prompt = patch.prompt
            if job.monitor_config and job.monitor_config.enabled:
                reset_reason = "prompt_change"
        if patch.model is not None:
            job.model = patch.model
        if patch.agent_id is not None:
            job.agent_id = patch.agent_id
        if patch.clear_project_id:
            job.project_id = None
        elif patch.project_id is not None:
            job.project_id = patch.project_id
        if patch.clear_workflow_template:
            job.workflow_template_id = None
            job.workflow_template_args = None
        else:
            if patch.workflow_template_id is not None:
                job.workflow_template_id = patch.workflow_template_id or None
            if patch.workflow_template_args is not None:
                job.workflow_template_args = patch.workflow_template_args or None
        if patch.command is not None and patch.command != job.command:
            job.command = patch.command
            if job.monitor_config and job.monitor_config.enabled:
                reset_reason = "command_change"
        if patch.delivery is not None:
            job.delivery = patch.delivery
        if patch.clear_failure_delivery:
            job.failure_delivery = None
        elif patch.failure_delivery is not None:
            job.failure_delivery = patch.failure_delivery
        if patch.clear_active_hours:
            job.active_hours = None
        elif patch.active_hours is not None:
            job.active_hours = patch.active_hours
        if patch.required_capabilities is not None:
            job.required_capabilities = patch.required_capabilities
        if patch.allowed_roots is not None:
            job.allowed_roots = patch.allowed_roots
        if patch.clear_tools_allowed:
            job.tools_allowed = None
        elif patch.tools_allowed is not None:
            job.tools_allowed = patch.tools_allowed
        if patch.clear_skill_ids:
            job.skill_ids = ()
        elif patch.skill_ids is not None:
            job.skill_ids = patch.skill_ids
        if patch.max_retries is not None:
            job.max_retries = patch.max_retries
        if patch.retry_backoff_ms is not None:
            job.retry_backoff_ms = patch.retry_backoff_ms
        if patch.timeout_seconds is not None:
            job.timeout_seconds = patch.timeout_seconds
        if patch.misfire_grace_seconds is not None:
            job.misfire_grace_seconds = patch.misfire_grace_seconds
        if patch.cooldown_seconds is not None:
            job.cooldown_seconds = patch.cooldown_seconds
        if patch.clear_max_fires:
            job.max_fires = None
        elif patch.max_fires is not None:
            job.max_fires = patch.max_fires
        if patch.clear_expires_at:
            job.expires_at = None
        elif patch.expires_at is not None:
            job.expires_at = patch.expires_at
        if patch.session_target is not None:
            job.session_target = patch.session_target
        if patch.clear_chat_id:
            job.chat_id = None
        elif patch.chat_id is not None:
            job.chat_id = patch.chat_id
        if patch.clear_failure_alert:
            job.failure_alert = False
        elif patch.failure_alert is not None:
            job.failure_alert = patch.failure_alert
        if patch.delete_after_run is not None:
            job.delete_after_run = patch.delete_after_run
        if patch.run_retention_days is not None:
            job.run_retention_days = patch.run_retention_days
        if patch.deduplicate is not None:
            job.deduplicate = patch.deduplicate
            if not patch.deduplicate:
                job.last_output_hash = None
        if patch.skip_if_active is not None:
            job.skip_if_active = patch.skip_if_active
        if patch.clear_monitor_config:
            job.monitor_config = None
        elif patch.monitor_config is not None:
            if (
                job.monitor_config
                and job.monitor_config.enabled
                and patch.monitor_config.monitor_type != job.monitor_config.monitor_type
            ):
                reset_reason = reset_reason or "monitor_type_change"
            job.monitor_config = patch.monitor_config
        if patch.clear_triggers:
            job.triggers = None
        elif patch.triggers is not None:
            job.triggers = self._ensure_webhook_credentials(patch.triggers)
        if patch.clear_context_from:
            job.context_from = ()
        elif patch.context_from is not None:
            await self._validate_context_from(job_id, patch.context_from)
            job.context_from = patch.context_from
        if patch.clear_pre_condition_script:
            job.pre_condition_script = None
        elif patch.pre_condition_script is not None:
            job.pre_condition_script = patch.pre_condition_script
        if patch.clear_acceptance_criteria:
            job.acceptance_criteria = ()
        elif patch.acceptance_criteria is not None:
            job.acceptance_criteria = patch.acceptance_criteria
        # After every field is applied: the slot depends on the schedule, the cooldown and the active window together.
        if activating:
            self._activate(job, now)
        elif job.status == JobStatus.ACTIVE and _moves_slot(job, patch):
            job.next_run_at = self._book_slot(job, now)
        job.updated_at = now

        if reset_reason:
            try:
                await self._reset_baseline_on_change(job_id, reset_reason)
            except Exception:
                logger.warning(
                    "Failed to auto-reset monitor baseline for job %s, baseline may be stale until next run",
                    job_id,
                    exc_info=True,
                )

        job = await self._store.save_job(job)
        self._scheduler.notify_change()
        return job
