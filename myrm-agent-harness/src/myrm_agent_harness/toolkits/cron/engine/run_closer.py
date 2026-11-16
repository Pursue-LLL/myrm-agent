"""Closing write of a run: the job's new state once the run has ended.

[INPUT]
- toolkits.cron.engine.helpers::classify_transient_error, error_backoff_ms, next_eligible_run, run_status_of (POS: pure engine helpers: error classification, backoff, the next slot to book and the status a run carries)
- toolkits.cron.engine.job_freshness::adopt_latest (POS: stored job as the truth before a closing write)
- toolkits.cron.protocols::CronStore (POS: job and run persistence)
- toolkits.cron.types::CronJob, JobResult, JobStatus, RunStatus, ScheduleKind (POS: Cron job domain types.)

[OUTPUT]
- RunCloserMixin: `_update_after_run` and its one-time and schedule-error branches, and `_record_trial_outcome` for a manual run, mixed into the executor

[POS]
Mixed into ``JobExecutor``. After a run is recorded, adopts the stored job and applies what the run decided: auto-pause
on a circuit break or on too many failures, the next slot or the backoff retry, completion of a one-time job (deleted
only when its run succeeded and its delivery did not fail), and the fallback when the schedule itself cannot be
computed. Because it writes onto the stored job, a pause, an edit or a
delete made while the run was in flight is neither undone nor resurrected. A manual run decides nothing about the
schedule or the job's state: it only becomes the job's latest run.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import (
    classify_transient_error,
    error_backoff_ms,
    next_eligible_run,
    run_status_of,
)
from myrm_agent_harness.toolkits.cron.engine.job_freshness import adopt_latest
from myrm_agent_harness.toolkits.cron.types import DeliveryStatus, JobStatus, RunStatus, ScheduleKind

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)

_SCHEDULE_ERROR_THRESHOLD = 3


class RunCloserMixin:
    """The closing write of a run for ``JobExecutor``.

    Accesses JobExecutor members via self: _store, _maybe_send_failure_alert.
    """

    _store: CronStore

    if TYPE_CHECKING:

        def _maybe_send_failure_alert(
            self, job: CronJob, failures: int, now: datetime, *, retry_safe: bool = True
        ) -> None: ...

    async def _update_after_run(
        self,
        job: CronJob,
        result: JobResult,
        new_failures: int,
        finished: datetime,
        delivery_status: DeliveryStatus = DeliveryStatus.SKIPPED,
    ) -> None:
        if not await adopt_latest(self._store, job):
            logger.info("Job %s was deleted during execution, skipping post-run update", job.id)
            return

        if job.schedule.kind == ScheduleKind.ONCE:
            await self._handle_once_completion(job, result, new_failures, finished, delivery_status)
            return

        if result.circuit_broken:
            job.status = JobStatus.PAUSED
            job.next_run_at = None
            logger.warning(
                "Job %s auto-paused due to circuit break: %s",
                job.id,
                result.error,
            )
        elif not result.success and new_failures > job.max_retries:
            job.status = JobStatus.PAUSED
            job.next_run_at = None
            logger.warning(
                "Job %s auto-paused: %d consecutive failures (max_retries=%d)",
                job.id,
                new_failures,
                job.max_retries,
            )
        elif result.success or not result.retry_safe:
            try:
                job.next_run_at = next_eligible_run(job, finished, last_run_at=finished)
            except Exception as exc:
                self._handle_schedule_compute_error(job, exc, finished)
        else:
            backoff = error_backoff_ms(new_failures)
            job.next_run_at = finished + timedelta(milliseconds=backoff)

        job.last_run_at = finished
        job.last_status = run_status_of(result)
        job.last_error = result.error if not result.success else None
        job.consecutive_failures = new_failures

        if result.success:
            job.last_failure_alert_at = None
        else:
            self._maybe_send_failure_alert(job, new_failures, finished, retry_safe=result.retry_safe)

        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    async def _record_trial_outcome(self, job: CronJob, result: JobResult, finished: datetime) -> None:
        """Close a manual run: it becomes the job's latest run and nothing else about the job moves.

        The schedule, fire count, failure streak and status stay as they are, so a trial can neither postpone a
        scheduled run, pause the job, nor complete or delete a one-time task. Only the stored job is written back,
        so an edit made while the trial ran is kept; the duplicate hash is the one value the run itself produced.
        """
        latest = await self._store.get_job(job.id)
        if latest is None:
            logger.info("Job %s was deleted during its manual run, skipping the post-run update", job.id)
            return
        latest.last_run_at = finished
        latest.last_status = run_status_of(result)
        latest.last_error = result.error if not result.success else None
        latest.last_output_hash = job.last_output_hash
        await self._store.save_job(latest)

    async def _handle_once_completion(
        self,
        job: CronJob,
        result: JobResult,
        new_failures: int,
        finished: datetime,
        delivery_status: DeliveryStatus = DeliveryStatus.SKIPPED,
    ) -> None:
        # A one-shot whose delivery failed keeps its job and run record: they hold the only copy of the result.
        if result.success and job.delete_after_run and delivery_status != DeliveryStatus.FAILED:
            await self._store.delete_job(job.id)
            return

        if result.success:
            job.status = JobStatus.COMPLETED
            job.consecutive_failures = 0
            job.last_failure_alert_at = None
        elif result.retry_safe and classify_transient_error(result.error or "") and new_failures <= job.max_retries:
            backoff = error_backoff_ms(new_failures)
            job.next_run_at = finished + timedelta(milliseconds=backoff)
            job.consecutive_failures = new_failures
            job.last_error = result.error
            logger.warning(
                "One-shot job %s: transient error, retrying in %dms (attempt %d/%d)",
                job.id,
                backoff,
                new_failures,
                job.max_retries,
            )
        else:
            job.status = JobStatus.PAUSED
            job.consecutive_failures = new_failures
            job.last_error = result.error
            self._maybe_send_failure_alert(job, new_failures, finished, retry_safe=result.retry_safe)

        if job.status != JobStatus.ACTIVE:
            job.next_run_at = None
        job.last_run_at = finished
        job.last_status = RunStatus.OK if result.success else RunStatus.ERROR
        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    def _handle_schedule_compute_error(self, job: CronJob, error: Exception, finished: datetime) -> None:
        """Handle schedule computation failure with fallback retry.

        Below threshold: sets a 60-second fallback next_run_at so the
        scheduler retries instead of leaving the job as a zombie.
        At threshold: auto-pauses the job.
        """
        job.consecutive_failures += 1
        if job.consecutive_failures >= _SCHEDULE_ERROR_THRESHOLD:
            job.status = JobStatus.PAUSED
            job.next_run_at = None
            logger.warning(
                "Job %s auto-paused: schedule expression keeps failing (%d times): %s",
                job.id,
                job.consecutive_failures,
                error,
            )
        else:
            job.next_run_at = finished + timedelta(seconds=60)
            logger.warning(
                "Job %s: schedule compute error (%s), will retry in 60s",
                job.id,
                error,
            )
