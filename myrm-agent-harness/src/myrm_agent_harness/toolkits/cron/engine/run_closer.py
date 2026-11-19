"""Closing write of a run: the job's new state once the run has ended.

[INPUT]
- toolkits.cron.engine.helpers::classify_transient_error, error_backoff_ms, next_eligible_run, pause_job, run_status_of (POS: pure engine helpers: error classification, backoff, the next slot to book, the one way a failure pauses a job and the status a run carries)
- toolkits.cron.engine.job_freshness::adopt_latest (POS: stored job as the truth before a closing write)
- toolkits.cron.protocols::CronStore (POS: job and run persistence)
- toolkits.cron.types::CronJob, JobResult, JobStatus, PauseReason, ScheduleKind (POS: Cron job domain types.)
- utils.text_utils::smart_truncate (POS: Text processing utilities. Provides token counting, language detection, smart truncation, and output sanitization.)

[OUTPUT]
- RunCloserMixin: `_update_after_run` and its recurring and one-time branches, `_pause_for_schedule_error` (also used by the skipped-run bookkeeping), and `_record_trial_outcome` for a manual run, mixed into the executor
- MAX_STORED_ERROR_CHARS, stored_error: the bound on the error text a run persists and the one way to apply it, shared by the run record (the executor) and the job's `last_error`

[POS]
Mixed into ``JobExecutor``. After a run is recorded, adopts the stored job and applies what the run decided: auto-pause
on a circuit break or on too many failures, the next slot or the backoff retry, completion of a one-time job (deleted
only when its run succeeded and its delivery did not fail), and the pause of a job whose schedule cannot be computed.
Every one of those pauses names its reason on the job (``paused_reason``). A job this write moves from active to
paused is reported once as a ``CronNotice``, whichever branch paused it. Because
it writes onto the stored job, a pause, an edit or a delete made while the run was in flight is neither undone nor
resurrected. A manual run decides nothing about the schedule or the job's state: it only becomes the job's latest
run. Closing a run sets ``last_error`` to its error, so a success clears it, a manual run's, a recurring job's and a
one-time job's alike. A skipped run never reaches this write. A schedule that cannot be computed names its own reason
there. Every decision reads the run's full error; the run record and ``last_error`` keep it bounded (``stored_error``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import (
    classify_transient_error,
    error_backoff_ms,
    next_eligible_run,
    pause_job,
    run_status_of,
)
from myrm_agent_harness.toolkits.cron.engine.job_freshness import adopt_latest
from myrm_agent_harness.toolkits.cron.types import DeliveryStatus, JobStatus, PauseReason, ScheduleKind
from myrm_agent_harness.utils.text_utils import smart_truncate

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)

# The error text of a run is persisted on the run record and on the job, and the job travels with every list call: a
# shell job's stderr can be megabytes, so only a bounded head and tail is stored.
MAX_STORED_ERROR_CHARS = 1000


def stored_error(error: str | None) -> str | None:
    """The error text as persisted: at most ``MAX_STORED_ERROR_CHARS``, its head and its tail kept.

    The tail is kept because the cause of a failure is usually its last line. Apply it where the text is written and
    nowhere earlier: the retry decision reads the run's full error, and a transient keyword the cut dropped would no
    longer be seen.
    """
    return smart_truncate(error, MAX_STORED_ERROR_CHARS) if error else None


class RunCloserMixin:
    """The closing write of a run for ``JobExecutor``.

    Accesses JobExecutor members via self: _store, _maybe_send_failure_alert, notify_paused.
    """

    _store: CronStore

    if TYPE_CHECKING:

        def _maybe_send_failure_alert(
            self, job: CronJob, failures: int, now: datetime, *, retry_safe: bool = True
        ) -> None: ...

        async def notify_paused(self, job: CronJob) -> None: ...

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

        # A job the user paused while the run was in flight was adopted as paused; only a pause this write makes is news.
        was_paused = job.status == JobStatus.PAUSED
        if job.schedule.kind == ScheduleKind.ONCE:
            await self._handle_once_completion(job, result, new_failures, finished, delivery_status)
        else:
            await self._close_recurring(job, result, new_failures, finished)

        # Judged once at the single exit, so every branch that pauses a job is covered, whichever branch it is.
        if job.status == JobStatus.PAUSED and not was_paused:
            await self.notify_paused(job)

    async def _close_recurring(
        self,
        job: CronJob,
        result: JobResult,
        new_failures: int,
        finished: datetime,
    ) -> None:
        """A recurring job's new state: paused, booked at its next regular slot, or booked for a backoff retry."""
        schedule_error: str | None = None
        if result.circuit_broken:
            pause_job(job, PauseReason.CIRCUIT_BREAK)
            logger.warning(
                "Job %s auto-paused due to circuit break: %s",
                job.id,
                result.error,
            )
        elif not result.success and new_failures > job.max_retries:
            pause_job(job, PauseReason.RUN_FAILURES)
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
                schedule_error = self._pause_for_schedule_error(job, exc)
        else:
            backoff = error_backoff_ms(new_failures)
            job.next_run_at = finished + timedelta(milliseconds=backoff)

        job.last_run_at = finished
        job.last_status = run_status_of(result)
        # Why the job stopped outranks the run's own error, which stays in the run record.
        job.last_error = stored_error(schedule_error or (result.error if not result.success else None))
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
        latest.last_error = stored_error(result.error if not result.success else None)
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

        # The job shows the run's own outcome: its error, or nothing once a retry succeeds. Written before the branches
        # because the failure alert the last one sends quotes it.
        job.last_error = stored_error(result.error if not result.success else None)

        if result.success:
            job.status = JobStatus.COMPLETED
            job.consecutive_failures = 0
            job.last_failure_alert_at = None
        # A circuit break is the loop guard's verdict that the run is stuck. Its message quotes the tool and arguments,
        # which can contain a transient keyword, so the keyword classifier must not send it back for another round.
        elif (
            result.retry_safe
            and not result.circuit_broken
            and classify_transient_error(result.error or "")
            and new_failures <= job.max_retries
        ):
            backoff = error_backoff_ms(new_failures)
            job.next_run_at = finished + timedelta(milliseconds=backoff)
            job.consecutive_failures = new_failures
            logger.warning(
                "One-shot job %s: transient error, retrying in %dms (attempt %d/%d)",
                job.id,
                backoff,
                new_failures,
                job.max_retries,
            )
        else:
            pause_job(job, PauseReason.CIRCUIT_BREAK if result.circuit_broken else PauseReason.RUN_FAILURES)
            job.consecutive_failures = new_failures
            self._maybe_send_failure_alert(job, new_failures, finished, retry_safe=result.retry_safe)

        if job.status != JobStatus.ACTIVE:
            job.next_run_at = None
        job.last_run_at = finished
        job.last_status = run_status_of(result)
        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    def _pause_for_schedule_error(self, job: CronJob, error: Exception) -> str:
        """Pause a job whose next slot cannot be computed and return the reason for its ``last_error``.

        The slot follows from the job's own schedule fields, so a retry fails the same way: re-arming the job
        would only run the agent again every minute until someone notices. The caller saves the job, and the
        pause is reported once it is saved.
        """
        pause_job(job, PauseReason.SCHEDULE_ERROR)
        logger.warning("Job %s auto-paused: its schedule cannot be computed: %s", job.id, error)
        return f"Schedule error: {error}"
