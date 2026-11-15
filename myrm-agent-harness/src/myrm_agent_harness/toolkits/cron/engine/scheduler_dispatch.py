"""Run dispatch for the cron scheduler: trigger-driven runs and the guarded path every run takes to the executor.

[INPUT]
- toolkits.cron.engine.helpers::auto_pause_notice, is_within_active_hours, pre_execution_check, resolve_stagger_ms (POS: pure engine helpers: guards, stagger and active hours)
- toolkits.cron.engine.job_freshness::adopt_latest (POS: stored job as the truth after the stagger and slot waits)
- toolkits.cron.engine.executor::JobExecutor (POS: job execution lifecycle manager)
- toolkits.cron.protocols::CronStore, JobRunner, TriggerProvider (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob, JobStatus, JobType (POS: Cron job domain types.)

[OUTPUT]
- SchedulerDispatchMixin: `dispatch_event`, `dispatch_system_event`, `dispatch_webhook` and the guarded execution path `_execute_and_persist`

[POS]
Mixed into ``CronScheduler``. Event, system-event and webhook triggers spawn runs through the same path as a due job:
the pre-execution guards, the active-hours window, ``skip_if_active``, the stagger delay, the runner lookup, the
concurrency slot and a last read of the stored job before the executor starts the run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import (
    auto_pause_notice,
    is_within_active_hours,
    pre_execution_check,
)
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    resolve_stagger_ms as _resolve_stagger_ms,
)
from myrm_agent_harness.toolkits.cron.engine.job_freshness import adopt_latest
from myrm_agent_harness.toolkits.cron.types import JobStatus

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
    from myrm_agent_harness.toolkits.cron.protocols import CronStore, JobRunner, TriggerProvider
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobType

logger = logging.getLogger(__name__)


class SchedulerDispatchMixin:
    """Trigger dispatch and the guarded execution path for ``CronScheduler``.

    Accesses CronScheduler members via self: _store, _runners, _trigger_provider, _executor, _active_jobs,
    _global_sem, _spawn.
    """

    _store: CronStore
    _runners: dict[JobType, JobRunner]
    _trigger_provider: TriggerProvider | None
    _executor: JobExecutor
    _active_jobs: set[str]
    _global_sem: asyncio.Semaphore

    if TYPE_CHECKING:

        def _spawn(self, coro: Coroutine[object, object, None]) -> None: ...

    async def dispatch_event(
        self,
        message: str,
        channel: str,
        user_id: str,
    ) -> int:
        """Check event triggers against an incoming message.

        Returns the number of jobs triggered.  When no ``TriggerProvider``
        is injected, returns 0 immediately.
        """
        if not self._trigger_provider:
            return 0
        try:
            jobs = await self._trigger_provider.check_event_triggers(message, channel, user_id)
        except Exception as exc:
            logger.warning("Event trigger check failed: %s", exc)
            return 0

        context = f"[TRIGGER: event]\nChannel: {channel}\nUser: {user_id}\nMessage: {message}"
        for job in jobs:
            self._spawn(self._execute_and_persist(job, context=context, trigger_source="event"))
        return len(jobs)

    async def dispatch_system_event(
        self,
        source: str,
        event_type: str,
        payload: dict[str, object],
    ) -> int:
        """Check system-event triggers.  Returns the number of jobs triggered."""
        if not self._trigger_provider:
            return 0
        try:
            jobs = await self._trigger_provider.check_system_event(source, event_type, payload)
        except Exception as exc:
            logger.warning("System event trigger check failed: %s", exc)
            return 0

        payload_str = json.dumps(payload, ensure_ascii=False, default=str)[:4000]
        context = f"[TRIGGER: system_event]\nSource: {source}\nEvent: {event_type}\nPayload:\n{payload_str}"
        for job in jobs:
            self._spawn(self._execute_and_persist(job, context=context, trigger_source="system_event"))
        return len(jobs)

    async def dispatch_webhook(
        self,
        path: str,
        secret: str,
        payload: dict[str, object],
    ) -> CronJob | None:
        """Validate and execute a webhook-triggered job.

        Returns the matched ``CronJob`` or ``None``.
        """
        if not self._trigger_provider:
            return None
        try:
            job = await self._trigger_provider.handle_webhook(path, secret, payload)
        except Exception as exc:
            logger.warning("Webhook trigger failed for path %s: %s", path, exc)
            return None

        if job is None:
            return None

        payload_str = json.dumps(payload, ensure_ascii=False, default=str)[:4000]
        context = f"[TRIGGER: webhook]\nPath: {path}\nPayload:\n{payload_str}"
        self._spawn(self._execute_and_persist(job, context=context, trigger_source="webhook"))
        return job

    async def _execute_and_persist(
        self,
        job: CronJob,
        *,
        context: str = "",
        trigger_source: str = "cron",
    ) -> None:
        try:
            now = datetime.now(UTC)
            skip_reason = pre_execution_check(job, now)
            if skip_reason:
                logger.warning("Job %s skipped: %s", job.id, skip_reason)
                pause_notice = auto_pause_notice(job, skip_reason)
                if pause_notice is not None:
                    await self._store.save_job(job)
                    await self._executor.emit_notice(pause_notice)
                return

            if not is_within_active_hours(job.active_hours):
                logger.warning("Job %s skipped: outside active hours", job.id)
                return

            if job.skip_if_active and job.id in self._active_jobs:
                logger.warning("Job %s skipped: previous instance still running (skip_if_active)", job.id)
                return

            stagger = _resolve_stagger_ms(job)
            if stagger > 0:
                delay_ms = random.randint(0, stagger)
                logger.warning("Job %s: stagger delay %dms", job.id, delay_ms)
                await asyncio.sleep(delay_ms / 1000)

            runner = self._runners.get(job.job_type)
            if not runner:
                logger.warning("No runner registered for job type %s", job.job_type)
                return

            self._active_jobs.add(job.id)
            try:
                async with self._global_sem:
                    # The waits above can last minutes; the stored job decides whether the run still happens.
                    if not await adopt_latest(self._store, job) or job.status != JobStatus.ACTIVE:
                        logger.info("Job %s was deleted or paused before it started, skipping", job.id)
                        return
                    job.fire_count += 1
                    await self._executor.run_and_record(
                        job,
                        runner,
                        context=context,
                        trigger_source=trigger_source,
                    )
            finally:
                self._active_jobs.discard(job.id)
        except Exception as exc:
            logger.warning("Unhandled error in job %s: %s", job.id, exc)
