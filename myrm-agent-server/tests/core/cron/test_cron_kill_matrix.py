"""A server killed at a fixed point of a run leaves no enabled job that will never run again.

A child process runs a real scheduler against a SQLite file and wraps one store method or the runner, so that the
process ends with ``os._exit(137)`` at the chosen point: no handler runs and nothing is flushed, which does to the file
what SIGKILL does. The parent then starts a new scheduler on the same file and reads what is left. Every point runs for
a recurring and for a one-time job. This module is also the child's entry point.

Runtime: about 5 s for the four cases (each child imports the application).
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
_RUNNER_RUNNING = "runner_running"
_RUN_RETURNED_UNWRITTEN = "run_returned_unwritten"
_POINTS = (_RUNNER_RUNNING, _RUN_RETURNED_UNWRITTEN)
_KINDS = ("recurring", "once")


class StalledJobError(AssertionError):
    """An enabled job without a next run time: nothing will ever run it."""


pytestmark = pytest.mark.xfail(
    raises=StalledJobError,
    strict=True,
    reason="a due job is claimed by clearing next_run_at before it runs; a process that dies afterwards leaves it "
    "enabled with no next run time, and nothing on restart revives a job that never ran",
)


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
            job = await manager.create_job("kill-matrix", JobType.AGENT, _schedule(kind), prompt="x", model="m")
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


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("point", _POINTS)
async def test_killed_run_leaves_no_stalled_job(point: str, kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
            jobs = await store.list_jobs()
        finally:
            await scheduler.stop()
    # A one-time job that the restart ran again and deleted is as good as one still waiting for its time.
    if any(job.status == JobStatus.ACTIVE and job.next_run_at is None for job in jobs):
        raise StalledJobError(f"the {kind} job killed at {point} is enabled without a next run time after the restart")


if __name__ == "__main__":
    asyncio.run(_die_in_child(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
