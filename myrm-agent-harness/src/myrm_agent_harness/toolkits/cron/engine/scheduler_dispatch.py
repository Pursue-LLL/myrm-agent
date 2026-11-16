"""Run dispatch for the cron scheduler: admission of due jobs, trigger-driven runs and the guarded path to the executor.

[INPUT]
- toolkits.cron.engine.helpers::auto_pause_notice, is_within_active_hours, next_slot_or_retry, pre_execution_check, resolve_stagger_ms (POS: pure engine helpers: guards, stagger, active hours and the next slot to book)
- toolkits.cron.engine.job_freshness::adopt_latest (POS: stored job as the truth after the stagger and slot waits)
- toolkits.cron.engine.executor::JobExecutor (POS: job execution lifecycle manager)
- toolkits.cron.protocols::CronStore, JobRunner, TriggerProvider (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob, JobStatus, JobType, ScheduleKind (POS: Cron job domain types.)

[OUTPUT]
- SchedulerDispatchMixin: `dispatch_event`, `dispatch_system_event`, `dispatch_webhook`, the admission `_admit` and the run path `_launch` → `_run` → `_dispatch`

[POS]
Mixed into ``CronScheduler``. A due recurring job is admitted by booking its next slot first; a one-shot, which has no
later slot, stays due until it completes. Every run, a due slot or an event, webhook or system-event trigger, is
registered as in flight by ``_launch`` before its task exists; its task writes the persisted in-flight marker first and
clears it when the job's last run ends, then the run passes the pre-execution guards, the active-hours window,
``skip_if_active``, the stagger delay, the runner lookup, the concurrency slot and a last read of the stored job before
the executor starts it.
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
    next_slot_or_retry,
    pre_execution_check,
)
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    resolve_stagger_ms as _resolve_stagger_ms,
)
from myrm_agent_harness.toolkits.cron.engine.job_freshness import adopt_latest
from myrm_agent_harness.toolkits.cron.types import JobStatus, ScheduleKind

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Coroutine

    from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
    from myrm_agent_harness.toolkits.cron.protocols import CronStore, JobRunner, TriggerProvider
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobType

logger = logging.getLogger(__name__)


class SchedulerDispatchMixin:
    """Admission, trigger dispatch and the guarded execution path for ``CronScheduler``.

    Accesses CronScheduler members via self: _store, _runners, _trigger_provider, _executor, _in_flight,
    _global_sem, _spawn.
    """

    _store: CronStore
    _runners: dict[JobType, JobRunner]
    _trigger_provider: TriggerProvider | None
    _executor: JobExecutor
    _in_flight: Counter[str]
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
            self._launch(job, context=context, trigger_source="event")
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
            self._launch(job, context=context, trigger_source="system_event")
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
        self._launch(job, context=context, trigger_source="webhook")
        return job

    async def _admit(self, job: CronJob) -> None:
        """Book a due recurring job's next slot, then launch the run that is due.

        Booking first keeps the stored job schedulable whatever happens to the run: a crash, a failed closing
        write or a refusing guard still leaves a next run time. The booking is one conditional write, so a job
        that was paused, deleted, edited or already dispatched meanwhile is not run. A one-shot has no later
        slot: it stays due until it completes, so a crash delivers it again instead of losing it.
        """
        if job.schedule.kind != ScheduleKind.ONCE:
            slot = next_slot_or_retry(job, datetime.now(UTC))
            try:
                advanced = await self._store.advance_next_run(job.id, next_run_at=slot)
            except Exception as exc:
                logger.warning("Job %s not dispatched: could not book its next run: %s", job.id, exc)
                return
            if not advanced:
                logger.info("Job %s not dispatched: it was paused, deleted, edited or already dispatched", job.id)
                return
        self._launch(job)

    def _launch(self, job: CronJob, *, context: str = "", trigger_source: str = "cron") -> None:
        """Register the run as in flight before its task exists, so no tick or trigger can slip in between."""
        self._in_flight[job.id] += 1
        self._spawn(self._run(job, context=context, trigger_source=trigger_source))

    async def _run(self, job: CronJob, *, context: str, trigger_source: str) -> None:
        """One run's task body: write the in-flight marker, dispatch, and clear the marker with the last run of the job.

        The marker is written before the stagger and concurrency waits, so a run that has not started yet but would
        be lost with the process is still reported. A cancelled run never closed its record: it keeps its marker, so
        the next start reports it; a graceful stop has already reported it and removed the marker.
        """
        cancelled = False
        try:
            await self._mark_running(job.id)
            await self._dispatch(job, context=context, trigger_source=trigger_source)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            self._in_flight[job.id] -= 1
            if not self._in_flight[job.id]:
                del self._in_flight[job.id]
                if not cancelled:
                    await self._clear_marker(job.id)

    async def _mark_running(self, job_id: str) -> None:
        """A marker that cannot be written costs the report of an interruption, never the run itself."""
        try:
            await self._store.mark_running(job_id)
        except Exception as exc:
            logger.warning(
                "Job %s: could not write its in-flight marker, an interruption would go unreported: %s", job_id, exc
            )

    async def _clear_marker(self, job_id: str) -> None:
        """Shielded: a cancel arriving mid-clear must not leave the marker of a finished run for the next start to report."""
        try:
            await asyncio.shield(self._store.clear_running(job_id))
        except Exception as exc:
            logger.warning(
                "Job %s: could not clear its in-flight marker, the next start will report an interruption: %s",
                job_id,
                exc,
            )

    async def _dispatch(
        self,
        job: CronJob,
        *,
        context: str = "",
        trigger_source: str = "cron",
    ) -> None:
        """Guards, stagger, runner lookup and the concurrency slot, then the executor. Registers nothing in flight."""
        try:
            now = datetime.now(UTC)
            scheduled = trigger_source == "cron"
            # A one-shot's instant is explicit: neither a cooldown nor the active window postpones it.
            once = job.schedule.kind == ScheduleKind.ONCE

            skip_reason = pre_execution_check(job, now)
            if skip_reason == "cooldown_active" and once:
                skip_reason = None
            if skip_reason:
                logger.warning("Job %s skipped: %s", job.id, skip_reason)
                pause_notice = auto_pause_notice(job, skip_reason)
                if pause_notice is not None:
                    job.next_run_at = None
                    await self._store.save_job(job)
                    await self._executor.emit_notice(pause_notice)
                elif scheduled:
                    await self._executor.record_guard_skip(job, reason=skip_reason, trigger_source=trigger_source)
                return

            if not once and not is_within_active_hours(job.active_hours):
                logger.warning("Job %s skipped: outside active hours", job.id)
                if scheduled:
                    await self._executor.record_guard_skip(
                        job, reason="outside_active_hours", trigger_source=trigger_source
                    )
                return

            if job.skip_if_active and self._in_flight[job.id] > 1:
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
        except Exception as exc:
            logger.warning("Unhandled error in job %s: %s", job.id, exc)
