"""Two-phase startup recovery strategy.

A recurring job's next slot is booked before its run starts (``CronScheduler._admit``), so an unclean shutdown
leaves every enabled job with a next run time and there is nothing to heal. Recovery only decides what to do with
the slots that came due while the process was down:

- **Phase 1 — Missed-Slot**: replay cron slots that fired during downtime.
- **Phase 2 — Grace Window**: execute due jobs still within misfire grace;
  skip and reschedule those past the grace period.

All recovery logic is encapsulated here; the scheduler only calls ``run()``.

[INPUT]
- toolkits.cron.engine.helpers::_ensure_utc, is_in_error_backoff, is_past_misfire_grace, next_slot_or_retry (POS: pure engine helpers: UTC normalisation, backoff, grace and the next slot to book)
- toolkits.cron.engine.parser::compute_prev_run (POS: Cron expression parsing and next-run calculation.)
- toolkits.cron.types::CronJob, JobStatus, RunStatus, ScheduleKind (POS: Cron job domain types.)
- toolkits.cron.protocols::CronStore (POS: Protocols for the cron toolkit.)

[OUTPUT]
- StartupRecovery: Encapsulates the two-phase startup recovery logic.

[POS]
Two-phase startup recovery strategy.
"""

from __future__ import annotations

import logging
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
    JobStatus,
    RunStatus,
    ScheduleKind,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronStore

logger = logging.getLogger(__name__)

AdmitFn = Callable[[CronJob], Awaitable[None]]


class StartupRecovery:
    """Encapsulates the two-phase startup recovery logic.

    Receives ``store`` for persistence and ``admit_fn`` as the scheduler's admission (``CronScheduler._admit``):
    it books a recurring job's next slot and launches the run that is due.
    """

    def __init__(self, store: CronStore, admit_fn: AdmitFn) -> None:
        self._store = store
        self._admit = admit_fn

    async def run(self) -> None:
        """Execute both recovery phases in order."""
        await self._replay_missed_slots()
        await self._execute_due_within_grace()

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
