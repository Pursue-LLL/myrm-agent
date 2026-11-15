"""Cron CRUD manager.

Orchestrates validation, persistence, and scheduler notification.
The ``CronManager`` is the single entry point for all job mutations
(used by both agent tools and API routes).

[INPUT]
- cron.engine.parser::compute_next_run (POS: cron expression parser and validator)
- cron.manager_queries::CronQueryMixin (POS: read-only queries of the cron CRUD manager)
- cron.manager_update::CronUpdateMixin (POS: update path of the cron CRUD manager)
- cron.manager_validation::CronValidationMixin (POS: validation half of the cron CRUD manager)
- cron.triggers::TriggerConfig, WebhookTrigger (POS: event trigger definitions)
- cron.types::CronJob, CronJobPatch, JobStatus, JobType, ScheduleKind, etc. (POS: cron data models)
- cron.protocols::CronStore (POS: cron job persistence protocol)
- cron.engine.scheduler::CronScheduler (POS: timer-based scheduling engine)

[OUTPUT]
- CronManager: single entry point for all cron job CRUD operations with validation and scheduler sync

[POS]
Cron CRUD orchestration layer. Validates job configurations, persists changes via CronStore,
and notifies CronScheduler of mutations. Used by both agent tools and API routes. Creation, duplication,
deletion, pause, resume and trigger live here; reads (``CronQueryMixin``), updates (``CronUpdateMixin``) and
field validation (``CronValidationMixin``) are mixed in.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.parser import compute_next_run
from myrm_agent_harness.toolkits.cron.manager_queries import CronQueryMixin
from myrm_agent_harness.toolkits.cron.manager_update import CronUpdateMixin
from myrm_agent_harness.toolkits.cron.manager_validation import CronValidationMixin
from myrm_agent_harness.toolkits.cron.triggers import TriggerConfig, WebhookTrigger
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    CronJob,
    CronJobPatch,
    DeliveryConfig,
    FailureAlertConfig,
    JobStatus,
    JobType,
    ScheduleKind,
    SessionTarget,
)

if TYPE_CHECKING:
    from myrm_agent_harness.infra.incremental.types import MonitorConfig
    from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
    from myrm_agent_harness.toolkits.cron.protocols import CronStore
    from myrm_agent_harness.toolkits.cron.types import Schedule

logger = logging.getLogger(__name__)


class CronManager(CronQueryMixin, CronUpdateMixin, CronValidationMixin):
    """CRUD orchestration for cron jobs.

    All mutations validate inputs, persist via ``CronStore``, and notify
    the ``CronScheduler`` so timer re-arms happen immediately.

    ``shell_enabled`` is set by the application layer (e.g. True in local mode,
    False in sandbox) to control whether shell jobs are allowed.
    """

    def __init__(
        self,
        store: CronStore,
        scheduler: CronScheduler,
        *,
        shell_enabled: bool = False,
    ) -> None:
        self._store = store
        self._scheduler = scheduler
        self._shell_enabled = shell_enabled

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def create_job(
        self,
        name: str,
        job_type: JobType,
        schedule: Schedule,
        *,
        prompt: str | None = None,
        model: str | None = None,
        chat_id: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        workflow_template_id: str | None = None,
        workflow_template_args: dict[str, str] | None = None,
        command: str | None = None,
        delivery: DeliveryConfig | None = None,
        failure_delivery: DeliveryConfig | None = None,
        failure_alert: FailureAlertConfig | bool | None = None,
        active_hours: ActiveHours | None = None,
        required_capabilities: tuple[str, ...] = (),
        allowed_roots: tuple[str, ...] = (),
        tools_allowed: tuple[str, ...] | None = None,
        skill_ids: tuple[str, ...] = (),
        max_retries: int = 2,
        retry_backoff_ms: int = 30_000,
        timeout_seconds: int = 300,
        misfire_grace_seconds: int = 300,
        cooldown_seconds: int = 0,
        max_fires: int | None = None,
        expires_at: datetime | None = None,
        session_target: SessionTarget = SessionTarget.ISOLATED,
        delete_after_run: bool | None = None,
        run_retention_days: int = 30,
        deduplicate: bool = False,
        skip_if_active: bool = False,
        monitor_config: MonitorConfig | None = None,
        triggers: TriggerConfig | None = None,
        context_from: tuple[str, ...] = (),
        pre_condition_script: str | None = None,
        acceptance_criteria: tuple[dict[str, object], ...] = (),
    ) -> CronJob:
        self._validate_create(job_type, schedule, prompt, command, pre_condition_script)

        if triggers:
            triggers = self._ensure_webhook_credentials(triggers)

        if delete_after_run is None:
            delete_after_run = schedule.kind == ScheduleKind.ONCE

        # Handle name conflicts: auto-append (2), (3), etc. if name exists
        final_name = await self._resolve_name_conflict(name)

        job_id = secrets.token_urlsafe(12)
        if context_from:
            await self._validate_context_from(job_id, context_from)

        now = datetime.now(UTC)
        try:
            job = CronJob(
                id=job_id,
                name=final_name,
                job_type=job_type,
                schedule=schedule,
                status=JobStatus.ACTIVE,
                prompt=prompt,
                model=model,
                chat_id=chat_id,
                agent_id=agent_id,
                project_id=project_id,
                workflow_template_id=workflow_template_id,
                workflow_template_args=workflow_template_args,
                command=command,
                required_capabilities=required_capabilities,
                allowed_roots=allowed_roots,
                tools_allowed=tools_allowed,
                skill_ids=skill_ids,
                delivery=delivery or DeliveryConfig(),
                failure_delivery=failure_delivery,
                failure_alert=None if failure_alert is True else failure_alert,
                active_hours=active_hours,
                max_retries=max_retries,
                retry_backoff_ms=retry_backoff_ms,
                timeout_seconds=timeout_seconds,
                misfire_grace_seconds=misfire_grace_seconds,
                cooldown_seconds=cooldown_seconds,
                max_fires=max_fires,
                expires_at=expires_at,
                session_target=session_target,
                delete_after_run=delete_after_run,
                run_retention_days=run_retention_days,
                deduplicate=deduplicate,
                skip_if_active=skip_if_active,
                monitor_config=monitor_config,
                triggers=triggers,
                context_from=context_from,
                pre_condition_script=pre_condition_script,
                acceptance_criteria=acceptance_criteria,
                next_run_at=compute_next_run(schedule, now),
                created_at=now,
                updated_at=now,
            )
        except ValueError as e:
            # Config validation failed — reject entire job, no fallback
            logger.error("Cron job config validation failed: %s", e)
            raise ValueError(f"Config validation failed: {e}") from e

        job = await self._store.save_job(job)
        self._scheduler.notify_change()
        logger.warning("Cron job created: %s (%s)", name, job.id)
        return job

    async def duplicate_job(self, job_id: str) -> CronJob | None:
        """Duplicate an existing job with all configuration fields.

        Every ``CronJob`` field is carried over except the identity (id, name,
        status, timestamps), the webhook credentials and the run state, which
        start fresh. A new configuration field is copied automatically; a new
        run-state field must be added to the reset below (the field tests fail until it is).
        The new job starts in PAUSED status to prevent accidental triggering.
        Webhook triggers get fresh path/secret to avoid conflicts.
        """
        source = await self._store.get_job(job_id)
        if source is None:
            return None

        triggers = source.triggers
        if triggers and triggers.webhooks:
            triggers = self._ensure_webhook_credentials(
                TriggerConfig(
                    webhooks=tuple(WebhookTrigger() for _ in triggers.webhooks),
                    events=triggers.events,
                    system_events=triggers.system_events,
                    polls=triggers.polls,
                    streams=triggers.streams,
                ),
            )

        copy_name = f"{source.name} (Copy)"
        final_name = await self._resolve_name_conflict(copy_name)

        new_id = secrets.token_urlsafe(12)
        now = datetime.now(UTC)
        cloned = replace(
            source,
            id=new_id,
            name=final_name,
            status=JobStatus.PAUSED,
            workflow_template_args=(dict(source.workflow_template_args) if source.workflow_template_args else None),
            triggers=triggers,
            fire_count=0,
            last_output_hash=None,
            next_run_at=None,
            last_run_at=None,
            last_status=None,
            last_error=None,
            consecutive_failures=0,
            last_failure_alert_at=None,
            created_at=now,
            updated_at=now,
        )
        cloned = await self._store.save_job(cloned)
        self._scheduler.notify_change()
        logger.warning("Cron job duplicated: %s -> %s (%s)", source.name, final_name, new_id)
        return cloned

    async def delete_job(self, job_id: str) -> bool:
        if await self._store.get_job(job_id) is None:
            return False
        deleted = await self._store.delete_job_cascade(job_id)
        if deleted:
            self._scheduler.notify_change()
        return deleted

    async def reset_monitor_baseline(self, job_id: str) -> bool:
        """Reset monitor baseline to restart incremental tracking.

        Args:
            job_id: Job identifier.

        Returns:
            True if baseline was reset, False if job not found or no baseline exists.

        Use cases:
            - Recover from corrupted baseline data
            - Restart monitoring after changing job scope
            - Testing and debugging
        """
        if await self._store.get_job(job_id) is None:
            return False

        state = await self._store.get_monitor_state(job_id)
        if not state:
            return False

        state.data = {}
        state.last_reset_at = datetime.now(UTC)
        state.last_reset_reason = "manual"
        await self._store.save_monitor_state(state)
        logger.info("Manually reset monitor baseline for job %s", job_id)

        return True

    async def pause_job(self, job_id: str) -> CronJob | None:
        return await self.update_job(job_id, CronJobPatch(status=JobStatus.PAUSED))

    async def resume_job(self, job_id: str) -> CronJob | None:
        job = await self._store.get_job(job_id)
        if not job:
            return None

        now = datetime.now(UTC)
        self._validate_resume_preconditions(job, now)

        job.status = JobStatus.ACTIVE
        job.next_run_at = compute_next_run(job.schedule, now)
        job.consecutive_failures = 0
        job.updated_at = now

        job = await self._store.save_job(job)
        self._scheduler.notify_change()
        return job

    async def trigger_now(self, job_id: str) -> bool:
        """Set next_run_at to now so the scheduler picks it up immediately."""
        job = await self._store.get_job(job_id)
        if not job or job.status != JobStatus.ACTIVE:
            return False

        job.next_run_at = datetime.now(UTC)
        await self._store.save_job(job)
        self._scheduler.notify_change()
        return True
