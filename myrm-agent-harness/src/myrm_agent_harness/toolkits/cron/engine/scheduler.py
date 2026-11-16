"""Cron scheduling engine.

Precise timer-based scheduler: computes exact sleep duration to the next due
job instead of fixed-interval polling.  Due jobs are dispatched into async
tasks bounded by a concurrency semaphore.

Execution lifecycle is delegated to ``JobExecutor``; startup recovery to
``StartupRecovery``; admission of due jobs, trigger dispatch and the guarded
execution path to ``SchedulerDispatchMixin``.  This module owns the timer
machinery, the tick that hands due jobs to admission and the stop, which
records the runs it cuts off before it cancels them.

[INPUT]
- cron.engine.executor::JobExecutor (POS: job execution lifecycle manager)
- cron.engine.helpers::_ensure_utc, is_past_misfire_grace (POS: scheduling helper utilities)
- cron.engine.recovery::StartupRecovery (POS: startup recovery for missed jobs)
- cron.engine.scheduler_dispatch::SchedulerDispatchMixin (POS: admission, trigger dispatch and the guarded execution path, mixed into the scheduler)
- cron.types::CronConfig, CronJob, JobType (POS: cron data models)

[OUTPUT]
- CronScheduler: precise timer-based scheduling engine with concurrency control and watchdog

[POS]
Cron scheduling engine. Computes exact sleep durations to the next due job, admits due
jobs (a recurring job's next slot is booked before its run starts) into async tasks with
semaphore-based concurrency control, and delegates execution to JobExecutor. A stop
records the in-flight runs as interrupted (not counted as failures), cancels them and
releases the lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.engine.helpers import _ensure_utc
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    is_past_misfire_grace as _is_past_grace,
)
from myrm_agent_harness.toolkits.cron.engine.recovery import StartupRecovery
from myrm_agent_harness.toolkits.cron.engine.scheduler_dispatch import SchedulerDispatchMixin
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    JobType,
)

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from myrm_agent_harness.toolkits.cron.protocols import (
        ConcurrencyLock,
        CronNoticeCallback,
        CronStore,
        JobRunner,
        PreFlightCondition,
        ResultDelivery,
        TriggerProvider,
    )
    from myrm_agent_harness.toolkits.cron.types import CronJob

logger = logging.getLogger(__name__)

_FALLBACK_RETRY_SECONDS = 30
_PURGE_INTERVAL_SECONDS = 86_400
_DEFAULT_RETENTION_DAYS = 30
_MIN_REFIRE_GAP_S = 2.0
# A host that embeds the scheduler may force-kill a slow exit after about two seconds: the runs' unwinding gets a
# fraction of that, so the lock release and the rest of the shutdown still fit.
_STOP_CANCEL_WAIT_S = 0.5
_WATCHDOG_INTERVAL_S = 60.0
# First tick after start: the health banner treats "no tick yet" as a startup warning,
# and waiting a full watchdog interval made every backend restart flash that banner.
_STARTUP_TICK_DELAY_S = 2.0


class CronScheduler(SchedulerDispatchMixin):
    """Precise timer-based cron scheduler.

    Instantiated once by the application layer, started in the server
    lifespan.  The ``notify_change`` callback is used by ``CronManager``
    after any job mutation to re-arm the timer.
    """

    def __init__(
        self,
        store: CronStore,
        runners: dict[JobType, JobRunner],
        delivery: ResultDelivery,
        config: CronConfig | None = None,
        lock: ConcurrencyLock | None = None,
        on_notice: CronNoticeCallback | None = None,
        trigger_provider: TriggerProvider | None = None,
        pre_condition: PreFlightCondition | None = None,
    ) -> None:
        cfg = config or CronConfig()
        self._store = store
        self._runners = runners
        self._lock = lock
        self._trigger_provider = trigger_provider

        self._running = False
        self._tick_in_progress = False
        self._timer_handle: asyncio.TimerHandle | None = None
        self._watchdog_handle: asyncio.TimerHandle | None = None
        self._last_tick_at: datetime | None = None
        self._startup_tick_pending = True
        self._tick_errors: int = 0
        self._global_sem = asyncio.Semaphore(cfg.max_concurrent)

        self._last_purge_at: datetime | None = None
        # Runs between launch and close, per job: the one place "running" lives.
        self._in_flight: Counter[str] = Counter()
        # Jobs whose due slot is being booked: their run launches right after, so a manual request must wait too.
        self._admitting: set[str] = set()
        self._bg_tasks: set[asyncio.Task[None]] = set()

        self._executor = JobExecutor(
            store=store,
            delivery=delivery,
            config=cfg,
            on_notice=on_notice,
            pre_condition=pre_condition,
        )
        self._recovery = StartupRecovery(
            store=store,
            admit_fn=self._admit,
            on_interrupted=self._executor.notify_interrupted,
        )

    def _spawn(self, coro: Coroutine[object, object, None]) -> None:
        """Schedule a tracked fire-and-forget task, guarding against premature GC."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify_change(self) -> None:
        """Re-arm the timer after a job mutation (called by CronManager)."""
        self._arm_timer()

    def health(self) -> dict[str, str | int | bool | None]:
        return {
            "running": self._running,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "tick_errors": self._tick_errors,
            "has_timer": self._timer_handle is not None or self._watchdog_handle is not None,
            "last_purge_at": self._last_purge_at.isoformat() if self._last_purge_at else None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return

        if self._lock:
            acquired = await self._lock.try_acquire("cron:scheduler:lock", ttl_seconds=60)
            if not acquired:
                logger.warning("Cron scheduler: another worker holds the lock, standing by")
                loop = asyncio.get_running_loop()
                loop.call_later(30, lambda: asyncio.ensure_future(self.start()))
                return

        self._running = True
        self._startup_tick_pending = True
        await self._recovery.run()
        self._arm_timer()
        logger.info("Cron scheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        if self._watchdog_handle:
            self._watchdog_handle.cancel()
            self._watchdog_handle = None
        if self._bg_tasks:
            await self._end_runs()
        if self._lock:
            await self._lock.release("cron:scheduler:lock")
        logger.info("Cron scheduler stopped")

    async def _end_runs(self) -> None:
        """Cut off the runs still going: leave a trace of each, cancel them, give them a moment to unwind.

        The traces come first and are not failures: the desktop shell force-kills a slow exit, and what was written
        before the unwind survives it. The wait is short for the same reason; a run that outlives it ends with the
        process, and its marker is already gone, so the next start reports nothing twice.
        """
        try:
            await self._recovery.report_interrupted(counted=False)
        except Exception as exc:
            logger.warning("Cron scheduler stop: could not record the interrupted runs: %s", exc)
        # Taken after the write: runs that finished meanwhile have left the set.
        tasks = list(self._bg_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=_STOP_CANCEL_WAIT_S)

    # ------------------------------------------------------------------
    # Timer machinery
    # ------------------------------------------------------------------

    def _arm_timer(self) -> None:
        if not self._running:
            return
        if self._timer_handle:
            self._timer_handle.cancel()
        with contextlib.suppress(RuntimeError):
            self._spawn(self._arm_timer_async())

    async def _arm_timer_async(self) -> None:
        try:
            next_wake = await self._store.earliest_next_run()
        except Exception as exc:
            logger.warning("Failed to query next run: %s — retrying in %ds", exc, _FALLBACK_RETRY_SECONDS)
            loop = asyncio.get_running_loop()
            self._timer_handle = loop.call_later(
                _FALLBACK_RETRY_SECONDS,
                lambda: loop.create_task(self._on_tick()),
            )
            return

        if next_wake is None:
            # A running scheduler with no due jobs still needs a live timer: the AppLayout
            # banner derives "stopped" from has_timer/last_tick, so an idle scheduler must
            # not look dead. The watchdog tick is a cheap no-op when nothing is due.
            self._arm_watchdog(_STARTUP_TICK_DELAY_S if self._startup_tick_pending else _WATCHDOG_INTERVAL_S)
            return

        delay = max(0.0, (_ensure_utc(next_wake) - datetime.now(UTC)).total_seconds())
        if delay == 0:
            delay = _MIN_REFIRE_GAP_S
        delay = min(delay, _WATCHDOG_INTERVAL_S)
        if self._startup_tick_pending:
            delay = min(delay, _STARTUP_TICK_DELAY_S)
        loop = asyncio.get_running_loop()
        self._timer_handle = loop.call_later(delay, lambda: loop.create_task(self._on_tick()))

    def _arm_watchdog(self, delay: float = _WATCHDOG_INTERVAL_S) -> None:
        """Keep a safety timer alive so the scheduler recovers from hangs."""
        if self._watchdog_handle:
            self._watchdog_handle.cancel()
        if not self._running:
            return
        try:
            loop = asyncio.get_running_loop()
            self._watchdog_handle = loop.call_later(
                delay,
                lambda: loop.create_task(self._on_tick()),
            )
        except RuntimeError:
            pass

    async def _on_tick(self) -> None:
        if not self._running:
            return
        if self._tick_in_progress:
            self._arm_watchdog()
            return
        self._tick_in_progress = True
        self._startup_tick_pending = False
        self._arm_watchdog()
        try:
            now = datetime.now(UTC)
            for job in await self._store.list_jobs(due_before=now):
                await self._handle_due(job, now)

            self._last_tick_at = now
            self._tick_errors = 0

            await self._maybe_purge_old_runs(now)
        except Exception as exc:
            self._tick_errors += 1
            logger.warning("Cron tick failed (errors=%d): %s", self._tick_errors, exc)
        finally:
            self._tick_in_progress = False
            self._arm_timer()

    async def _handle_due(self, job: CronJob, now: datetime) -> None:
        """Admit a due job, or reschedule it when its slot is past the misfire grace.

        A job that is still in flight waits: its run books the next slot when it closes. A failure here is
        confined to this job: its due time stays booked, so the same failure repeats on every tick, and it must
        not hold back the jobs behind it.
        """
        if self._in_flight[job.id]:
            return
        try:
            if _is_past_grace(job, now):
                logger.warning("Job %s skipped: past misfire grace", job.id)
                await self._recovery.reschedule_skipped(job.id)
            else:
                await self._admit(job)
        except Exception as exc:
            logger.warning("Cron tick: job %s could not be handled: %s", job.id, exc)

    # ------------------------------------------------------------------
    # Run record housekeeping
    # ------------------------------------------------------------------

    async def _maybe_purge_old_runs(self, now: datetime) -> None:
        if self._last_purge_at and (now - self._last_purge_at).total_seconds() < _PURGE_INTERVAL_SECONDS:
            return
        try:
            cutoff = now - timedelta(days=_DEFAULT_RETENTION_DAYS)
            deleted = await self._store.purge_old_runs(before=cutoff)
            self._last_purge_at = now
            if deleted > 0:
                logger.warning("Purged %d old cron run records (before %s)", deleted, cutoff.isoformat())
        except Exception as exc:
            logger.warning("Failed to purge old runs: %s", exc)
