"""A server killed at a fixed point of a run leaves no enabled job that will never run again and no unreported run.

A child process runs a real scheduler against a SQLite file and wraps one store method or the runner, so that the
process ends with ``os._exit(137)`` at the chosen point: no handler runs and nothing is flushed, which does to the file
what SIGKILL does. The parent then starts a new scheduler on the same file and reads what is left: no stalled job, no
marker, and one interrupted-run record, counted as a failure, for every run that had begun. Every point runs for a
recurring and for a one-time job, except the one between booking and start, which only a recurring job has: a one-time
job is never booked. A one-time job is delivered again by the restart, and that delivery succeeds, so its failures end
at zero. A run that closed and died before it deleted its marker is reported as interrupted too: the restart cannot
tell it from a run that never closed. This module is also the child's entry point.

Runtime: about 6 s for the seven cases (each child imports the application).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from tests.support.policy_sqlite import policy_database

_KILLED = 137
_SURVIVED = 3  # the child reached the end without dying: the injection point was never hit
_CHILD_PATIENCE_S = 20
_WAIT_S = 30
_NO_TIMER_S = 3600.0
_BOOKED_NOT_STARTED = "booked_not_started"
_RUNNER_RUNNING = "runner_running"
_RUN_RETURNED_UNWRITTEN = "run_returned_unwritten"
_MARKER_KEPT = "marker_kept"
_INTERRUPTED = "Interrupted:"
# (point, kind, interrupted-run records after the restart, the job's consecutive failures after the restart)
_CASES = [
    (_RUNNER_RUNNING, "recurring", 1, 1),
    (_RUNNER_RUNNING, "once", 1, 0),
    (_RUN_RETURNED_UNWRITTEN, "recurring", 1, 1),
    (_RUN_RETURNED_UNWRITTEN, "once", 1, 0),
    (_MARKER_KEPT, "recurring", 1, 1),
    (_MARKER_KEPT, "once", 1, 1),
    (_BOOKED_NOT_STARTED, "recurring", 0, 0),
]


class _Runner:
    def __init__(self, *, die: bool) -> None:
        self.die = die

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        if self.die:
            os._exit(_KILLED)
        return JobResult(success=True, output="ok")


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


def _schedule(kind: str) -> Schedule:
    if kind == "once":
        return Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1))
    return Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000)


def _stack(store: SqlAlchemyCronStore, runner: _Runner) -> tuple[CronScheduler, CronManager]:
    scheduler = CronScheduler(
        store=store, runners={JobType.AGENT: runner}, delivery=_Delivery(), config=CronConfig(max_concurrent=4)
    )
    return scheduler, CronManager(store=store, scheduler=scheduler)


async def _die_in_child(db: Path, kind: str, point: str) -> None:
    """Create a due job, tick once, and die when the run reaches ``point``."""
    with pytest.MonkeyPatch.context() as patch:
        async with policy_database(db, patch):
            store = SqlAlchemyCronStore()
            scheduler, manager = _stack(store, _Runner(die=point == _RUNNER_RUNNING))
            if point == _RUN_RETURNED_UNWRITTEN:

                async def die(_run: object) -> None:
                    os._exit(_KILLED)

                patch.setattr(store, "save_run", die)
            if point == _MARKER_KEPT:

                async def die_before_clear(_job_id: str) -> None:
                    os._exit(_KILLED)

                patch.setattr(store, "clear_running", die_before_clear)
            if point == _BOOKED_NOT_STARTED:
                book = store.advance_next_run

                async def die_once_booked(job_id: str, *, next_run_at: datetime) -> bool:
                    await book(job_id, next_run_at=next_run_at)
                    os._exit(_KILLED)

                patch.setattr(store, "advance_next_run", die_once_booked)
            # A one-time job is kept after its run, so the restart's records can be read.
            job = await manager.create_job(
                "kill-matrix", JobType.AGENT, _schedule(kind), prompt="x", model="m", delete_after_run=False
            )
            stored = await store.get_job(job.id)
            assert stored is not None
            stored.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
            await store.save_job(stored)
            await scheduler.start()
            await scheduler._on_tick()
            await asyncio.sleep(_CHILD_PATIENCE_S)
    sys.exit(_SURVIVED)


def _child_env(data_dir: Path) -> dict[str, str]:
    """The child imports what the parent imports and keeps its data under the test's directory."""
    return {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in sys.path if path), "MYRM_DATA_DIR": str(data_dir)}


def _tasks() -> list[asyncio.Task[object]]:
    me = asyncio.current_task()
    return [task for task in asyncio.all_tasks() if task is not me and not task.done()]


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the restart's own recovery may act: the scheduler's timers must never fire."""
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, _NO_TIMER_S)


@pytest.mark.parametrize(
    ("point", "kind", "interrupted", "failures"), _CASES, ids=[f"{point}-{kind}" for point, kind, *_ in _CASES]
)
async def test_a_killed_run_is_reported_once_and_leaves_no_stalled_job_or_marker(
    point: str, kind: str, interrupted: int, failures: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "cron.db"
    command = [sys.executable, "-P", str(Path(__file__)), str(db), kind, point]
    child = await asyncio.to_thread(
        subprocess.run, command, env=_child_env(tmp_path), capture_output=True, text=True, timeout=_CHILD_PATIENCE_S + 60
    )
    assert child.returncode == _KILLED, f"the child did not die at {point}: exit {child.returncode}\n{child.stderr[-2000:]}"

    async with policy_database(db, monkeypatch):
        store = SqlAlchemyCronStore()
        scheduler, _ = _stack(store, _Runner(die=False))
        await scheduler.start()
        try:
            async with asyncio.timeout(_WAIT_S):
                while pending := _tasks():
                    await asyncio.gather(*pending, return_exceptions=True)
            (job,) = await store.list_jobs()
            runs = await store.list_runs(limit=100)
            markers = await store.list_running()
        finally:
            await scheduler.stop()
    where = f"the {kind} job killed at {point}"
    assert not (job.status == JobStatus.ACTIVE and job.next_run_at is None), f"{where} is enabled without a next run"
    assert markers == [], f"{where} left a marker behind after the restart"
    reported = [run for run in runs if (run.error or "").startswith(_INTERRUPTED)]
    assert len(reported) == interrupted, f"{where} has {len(reported)} interrupted-run records, expected {interrupted}"
    assert job.consecutive_failures == failures, f"{where} counts {job.consecutive_failures} failures, expected {failures}"


if __name__ == "__main__":
    asyncio.run(_die_in_child(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
