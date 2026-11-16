"""Recording of runs that did not execute to completion: skipped and deferred.

[INPUT]
- toolkits.cron.engine.job_freshness::adopt_latest (POS: stored job as the truth before a closing write)
- toolkits.cron.engine.helpers::next_eligible_run (POS: pure engine helpers: the next slot to book)
- toolkits.cron.protocols::CronStore (POS: job and run persistence)
- toolkits.cron.triggers::TriggerKind (POS: Trigger type definitions and security helpers.)
- toolkits.cron.types::CronJob, CronRunRecord, JobResult (POS: Cron job domain types.)

[OUTPUT]
- SkippedRunMixin: `_record_skipped` / `_record_deferred`, their probe / runner entry points and `record_guard_skip`

[POS]
Mixed into ``JobExecutor``. A skipped run advances the schedule without counting a
failure; a deferred run re-arms the job at the instant the runner says a repeat can
succeed; a dispatch guard's refusal (cooldown, active hours) is a skipped run that never
began, so it leaves the last run time alone. None of them touches incremental monitors or
delivery, and none spends ``max_fires``: the scheduler counts a fire when the run starts,
and nothing executed. All write onto the stored job (``adopt_latest``): a job the user
paused stays paused, and a deleted one is neither recorded nor brought back. A manual run
that is skipped or deferred leaves only its run record: the schedule and the job's state
are not its to change.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import next_eligible_run
from myrm_agent_harness.toolkits.cron.engine.job_freshness import adopt_latest
from myrm_agent_harness.toolkits.cron.triggers import TriggerKind
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    DeliveryStatus,
    JobResult,
    JobStatus,
    RunStatus,
    ScheduleKind,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore

logger = logging.getLogger(__name__)


class SkippedRunMixin:
    """Skipped / deferred run bookkeeping for ``JobExecutor``.

    Accesses JobExecutor members via self: _store, _handle_schedule_compute_error. The run's trigger source is a
    parameter of every entry point: runs of one executor overlap, so it cannot live on the instance.
    """

    _store: CronStore

    if TYPE_CHECKING:

        def _handle_schedule_compute_error(self, job: CronJob, error: Exception, finished: datetime) -> None: ...

    async def record_guard_skip(self, job: CronJob, *, reason: str, trigger_source: str) -> None:
        """A dispatch guard refused a due run: record it as SKIPPED and book the job's next slot."""
        await self._record_skipped(job, trigger_source=trigger_source, reason=reason, attempted=False)

    async def _record_skipped(
        self, job: CronJob, *, trigger_source: str, reason: str | None = None, attempted: bool = True
    ) -> None:
        """Record a SKIPPED run and advance job schedule.

        Used by pre-flight probe skips, runner-level skips (e.g. heartbeat no-content) and dispatch-guard
        refusals.  ``attempted`` is False for a refusal: that run never began, so no fire is handed back and the
        job's last run time, which anchors the cooldown, stays where it was.  Does not touch monitors.
        """
        if not await adopt_latest(self._store, job):
            logger.info("Job %s was deleted during execution, skipping its skipped-run record", job.id)
            return
        if trigger_source == TriggerKind.MANUAL:
            await self._save_skipped_run(job, datetime.now(UTC), reason, trigger_source=trigger_source)
            return
        if attempted:
            self._refund_fire(job)
        now = datetime.now(UTC)
        await self._save_skipped_run(job, now, reason, trigger_source=trigger_source)

        if job.schedule.kind in (ScheduleKind.CRON, ScheduleKind.INTERVAL):
            try:
                job.next_run_at = next_eligible_run(job, now)
            except Exception as e:
                self._handle_schedule_compute_error(job, e, now)
        elif job.schedule.kind == ScheduleKind.ONCE:
            if job.delete_after_run:
                await self._store.delete_job(job.id)
                return
            job.status = JobStatus.COMPLETED
            job.next_run_at = None

        if attempted:
            job.last_run_at = now
        job.last_status = RunStatus.SKIPPED
        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    async def _record_deferred(self, job: CronJob, result: JobResult, *, trigger_source: str) -> None:
        """Re-arm *job* at ``result.retry_at``: a SKIPPED run, no failure counted, schedule kept.

        Retrying before that instant only burns attempts, and failing would auto-pause the job.
        """
        if not await adopt_latest(self._store, job):
            logger.info("Job %s was deleted during execution, skipping deferral", job.id)
            return
        now = datetime.now(UTC)
        reason = result.skip_reason or result.error
        if trigger_source == TriggerKind.MANUAL:
            await self._save_skipped_run(job, now, reason, trigger_source=trigger_source)
            return
        self._refund_fire(job)
        await self._save_skipped_run(job, now, reason, trigger_source=trigger_source)

        job.next_run_at = result.retry_at
        job.last_run_at = now
        job.last_status = RunStatus.SKIPPED
        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    async def _record_skipped_by_probe(self, job: CronJob, *, trigger_source: str) -> None:
        """Handle a job skipped by the pre-flight probe."""
        await self._record_skipped(job, trigger_source=trigger_source, reason="pre-flight-condition")

    async def _record_skipped_by_runner(self, job: CronJob, reason: str | None, *, trigger_source: str) -> None:
        """Handle a job skipped by the runner (e.g. heartbeat no-content)."""
        await self._record_skipped(job, trigger_source=trigger_source, reason=reason)

    @staticmethod
    def _refund_fire(job: CronJob) -> None:
        """Hand back the fire the scheduler counted at run start: a run that never executed spends no ``max_fires``."""
        job.fire_count = max(job.fire_count - 1, 0)

    async def _save_skipped_run(self, job: CronJob, now: datetime, reason: str | None, *, trigger_source: str) -> None:
        await self._store.save_run(
            CronRunRecord(
                id=secrets.token_urlsafe(12),
                job_id=job.id,
                trigger_source=trigger_source,
                status=RunStatus.SKIPPED,
                started_at=now,
                finished_at=now,
                duration_ms=0,
                delivery_status=DeliveryStatus.SKIPPED,
                output=reason,
            )
        )
