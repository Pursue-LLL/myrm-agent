"""Cron run rows for the tests that count failures, shared by the nav badge and the ops snapshot tests.

[INPUT]
- app.core.cron.adapters.sqlalchemy_store::SqlAlchemyCronStore (POS: the SQL store whose rows the counts read)

[OUTPUT]
- seed_runs_with_two_recent_failures: store one job with runs of every status, two of them failures of the last day
- FAILURES_IN_THE_LAST_DAY: how many failures that is

[POS]
A count of failed runs is only faithful against real rows: the status set it selects is part of what is under test.
Call it inside `policy_database(...)`, which points the store at the test database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.cron import (
    CronJob,
    CronRunRecord,
    JobType,
    Schedule,
    ScheduleKind,
)
from myrm_agent_harness.toolkits.cron import (
    RunStatus as CronRunStatus,
)

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore

FAILURES_IN_THE_LAST_DAY = 2


async def seed_runs_with_two_recent_failures() -> None:
    """Store a job and its runs: an ok, an error, a circuit break and a skipped run just now, a circuit break last week.

    The error and the circuit break of the last 24 hours are the failures; the older circuit break is outside the window.
    """
    now = datetime.now(UTC)
    runs = [
        ("ok", CronRunStatus.OK, now),
        ("error", CronRunStatus.ERROR, now),
        ("breaker", CronRunStatus.CIRCUIT_BREAK, now),
        ("skipped", CronRunStatus.SKIPPED, now),
        ("last-week", CronRunStatus.CIRCUIT_BREAK, now - timedelta(days=7)),
    ]
    store = SqlAlchemyCronStore()
    await store.save_job(
        CronJob(
            id="job",
            name="job",
            job_type=JobType.ROUTER,
            schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
            command="__probe__",
        )
    )
    for run_id, status, started_at in runs:
        await store.save_run(
            CronRunRecord(
                id=run_id,
                job_id="job",
                started_at=started_at,
                finished_at=started_at + timedelta(seconds=5),
                duration_ms=5_000,
                status=status,
            )
        )
