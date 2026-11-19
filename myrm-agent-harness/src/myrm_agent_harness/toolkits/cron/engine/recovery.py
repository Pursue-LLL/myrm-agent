"""Startup recovery: report the runs a dead process left behind, then replay what came due while it was down.

A recurring job's next slot is booked before its run starts (``CronScheduler._admit``), so an unclean shutdown
leaves every enabled job with a next run time and there is nothing to heal. What a dead process does leave is the
in-flight marker of each run it was making: recovery turns those into interrupted-run records first, then decides
what to do with the slots that came due while the process was down:

- **Interrupted runs**: every marker left behind becomes an error run record and one counted failure, and the
  application is told about each (``on_interrupted``).
- **Phase 1 — Missed-Slot**: replay cron slots that fired during downtime.
- **Phase 2 — Grace Window**: execute due jobs still within misfire grace;
  skip and reschedule those past the grace period.

All recovery logic is encapsulated here; the scheduler calls ``run()`` at start and ``report_interrupted`` at stop.

[INPUT]
- toolkits.cron.engine.helpers::_ensure_utc, is_in_error_backoff, is_past_misfire_grace, next_slot_or_retry (POS: pure engine helpers: UTC normalisation, backoff, grace and the next slot to book)
- toolkits.cron.engine.parser::compute_prev_run (POS: Cron expression parsing and next-run calculation.)
- toolkits.cron.types::CronJob, CronRunRecord, DeliveryStatus, JobStatus, RunStatus, ScheduleKind (POS: Cron job domain types.)
- toolkits.cron.protocols::CronStore (POS: Protocols for the cron toolkit.)

[OUTPUT]
- StartupRecovery: reports interrupted runs (`report_interrupted`, telling `on_interrupted` about each crashed one) and runs the startup recovery phases (`run`).

[POS]
Startup recovery strategy, and the one place that turns an in-flight marker into an interrupted-run record.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import (
    _ensure_utc,
)
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    is_in_error_backoff as _is_in_error_backoff,
)
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    is_past_misfire_grace as _is_past_grace,
)
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    next_slot_or_retry as _next_slot_or_retry,
)
from myrm_agent_harness.toolkits.cron.engine.parser import compute_prev_run
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    DeliveryStatus,
    JobStatus,
    RunStatus,
    ScheduleKind,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore

logger = logging.getLogger(__name__)

AdmitFn = Callable[[CronJob], Awaitable[None]]
InterruptedFn = Callable[[CronJob], Awaitable[None]]

_CRASH_MESSAGE = "Interrupted: the server stopped before this run finished"
_STOP_MESSAGE = "Interrupted: the application was stopping before this run finished"


class StartupRecovery:
    """Reports interrupted runs and replays what came due during downtime.

    Receives ``store`` for persistence and ``admit_fn`` as the scheduler's admission (``CronScheduler._admit``):
    it books a recurring job's next slot and launches the run that is due. ``on_interrupted`` gets the saved job of
    each run a crash cut short, once its record and failure count are stored (a graceful stop is not announced).
    """

    def __init__(
        self,
        store: CronStore,
        admit_fn: AdmitFn,
        on_interrupted: InterruptedFn | None = None,
    ) -> None:
        self._store = store
        self._admit = admit_fn
        self._on_interrupted = on_interrupted

    async def run(self) -> None:
        """Report the runs the previous process left in flight, then execute both recovery phases in order.

        Every marker in the store is read as the trace of a dead process, which holds because the scheduler lock
        never passes to another process while its holder is alive (``ConcurrencyLock``).
        """
        await self.report_interrupted(counted=True)
        await self._replay_missed_slots()
        await self._execute_due_within_grace()

    # ------------------------------------------------------------------
    # Interrupted runs
    # ------------------------------------------------------------------

    async def report_interrupted(self, *, counted: bool) -> None:
        """Record each run still marked in flight as an interrupted run and drop its marker.

        ``counted`` at startup: the marker outlived its process, so the process died under the run. The run spends
        a failure like any failing run, which pauses a job whose every run kills the server instead of restarting
        it forever. At a graceful stop the scheduler itself ends the run, which is no fault of the job: nothing is
        counted. The marker goes first: a report lost to a second crash is better than one run counted twice. One
        job's failure to record is logged and does not hold back the others.
        """
        for job_id, started in await self._store.list_running():
            try:
                await self._store.clear_running(job_id)
                await self._record_interrupted(job_id, _ensure_utc(started), counted=counted)
            except Exception as exc:
                logger.warning("Job %s: could not record its interrupted run: %s", job_id, exc)

    async def _record_interrupted(self, job_id: str, started: datetime, *, counted: bool) -> None:
        job = await self._store.get_job(job_id)
        if job is None:
            return
        message = _CRASH_MESSAGE if counted else _STOP_MESSAGE
        # A crash leaves no end time: stretching the unknown to the moment it was noticed would show hours of work.
        ended = started if counted else datetime.now(UTC)
        await self._store.save_run(
            CronRunRecord(
                id=secrets.token_urlsafe(12),
                job_id=job_id,
                trigger_source="recovery" if counted else "shutdown",
                status=RunStatus.ERROR,
                started_at=started,
                finished_at=ended,
                duration_ms=int((ended - started).total_seconds() * 1000),
                error=message,
                delivery_status=DeliveryStatus.SKIPPED,
            )
        )
        job.last_status = RunStatus.ERROR
        job.last_error = message
        if counted:
            job.consecutive_failures += 1
            if job.consecutive_failures > job.max_retries:
                job.status = JobStatus.PAUSED
                job.next_run_at = None
        await self._store.save_job(job)
        # A crash is a fault worth a warning; a stop the application asked for is routine.
        logger.log(
            logging.WARNING if counted else logging.INFO,
            "Job %s: recorded an interrupted run (counted=%s)",
            job_id,
            counted,
        )
        if counted:
            await self._announce(job)

    async def _announce(self, job: CronJob) -> None:
        """Tell the application a crash cut the job's run short; a failing callback costs the notice, not the report."""
        if self._on_interrupted is None:
            return
        try:
            await self._on_interrupted(job)
        except Exception as exc:
            logger.warning("Job %s: the interrupted-run notice failed: %s", job.id, exc)

    # ------------------------------------------------------------------
    # Phase 1: Missed-Slot replay
    # ------------------------------------------------------------------

    async def _replay_missed_slots(self) -> None:
        """Re-execute cron slots missed during downtime."""
        now = datetime.now(UTC)
        replay: list[CronJob] = []

        for job in await self._store.list_jobs():
            if job.status != JobStatus.ACTIVE or job.schedule.kind != ScheduleKind.CRON or job.last_run_at is None:
                continue
            if _is_in_error_backoff(job, now):
                continue

            # A slot that elapsed before the last edit or resume was never owed to anyone.
            anchor = max(_ensure_utc(job.last_run_at), _ensure_utc(job.updated_at))
            prev_slot = compute_prev_run(job.schedule, now)
            if prev_slot and prev_slot > anchor:
                replay.append(job)

        if not replay:
            return

        logger.warning("Replaying %d missed cron slots after restart", len(replay))
        for job in replay:
            await self._admit(job)

    # ------------------------------------------------------------------
    # Phase 2: Grace-window execution
    # ------------------------------------------------------------------

    async def _execute_due_within_grace(self) -> None:
        """Execute jobs past due but still within misfire grace; reschedule the ones past it."""
        now = datetime.now(UTC)
        runnable: list[CronJob] = []

        for job in await self._store.list_jobs(due_before=now):
            if _is_past_grace(job, now):
                logger.warning("Startup skip: job %s past misfire grace", job.id)
                await self.reschedule_skipped(job.id)
            elif not _is_in_error_backoff(job, now):
                runnable.append(job)

        if runnable:
            logger.warning("Cron scheduler: catching up %d due jobs", len(runnable))
            for job in runnable:
                await self._admit(job)

    async def reschedule_skipped(self, job_id: str) -> None:
        """Re-compute next_run for a job skipped due to misfire grace."""
        job = await self._store.get_job(job_id)
        if not job or job.status != JobStatus.ACTIVE:
            return
        now = datetime.now(UTC)
        if job.schedule.kind == ScheduleKind.ONCE:
            job.status = JobStatus.COMPLETED
            job.next_run_at = None
        else:
            job.next_run_at = _next_slot_or_retry(job, now)
        job.last_status = RunStatus.SKIPPED
        job.updated_at = now
        await self._store.save_job(job)
