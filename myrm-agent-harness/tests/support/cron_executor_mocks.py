"""A `JobExecutor` over a mocked store and delivery, and the job builders its unit tests share.

[INPUT]
- toolkits.cron.engine.executor::JobExecutor (POS: the run-and-record engine under test)
- toolkits.cron.types::CronConfig, CronJob, DeliveryConfig, JobStatus, JobType, Schedule, ScheduleKind (POS: the job model the builders fill in)

[OUTPUT]
- make_schedule: a cron-expression schedule, or a one-time schedule an hour ahead
- make_job: an active agent job with a chat delivery; any field can be overridden
- make_executor: a `JobExecutor` over an `AsyncMock` store and an `AsyncMock` delivery, returned with both mocks
- store_holds: make the mocked store answer `get_job` with the job under test, as a store holds a dispatched job

[POS]
Pytest-only helper shared by the `JobExecutor` unit tests: a test states the job and reads the store and delivery
mocks back, without wiring a scheduler.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)


def make_schedule(kind: ScheduleKind = ScheduleKind.CRON) -> Schedule:
    if kind == ScheduleKind.ONCE:
        return Schedule(kind=kind, run_at=datetime.now(UTC) + timedelta(hours=1))
    return Schedule(kind=kind, expr="0 * * * *")


# Tests override any job field by name, so the constructor is called through a variadic callable: a
# `**dict[str, object]` expansion is checked against every field type and rejected.
_new_job: Callable[..., CronJob] = CronJob


def make_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "job-1",
        "name": "Test Job",
        "job_type": JobType.AGENT,
        "schedule": make_schedule(),
        "status": JobStatus.ACTIVE,
        "prompt": "test prompt",
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return _new_job(**defaults)


def make_executor(
    *,
    config: CronConfig | None = None,
) -> tuple[JobExecutor, AsyncMock, AsyncMock]:
    store = AsyncMock()
    store.save_job = AsyncMock(side_effect=lambda j: j)
    store.save_run = AsyncMock()
    store.delete_job = AsyncMock(return_value=True)
    store.get_job = AsyncMock(side_effect=lambda job_id: make_job(id=job_id))
    delivery = AsyncMock()
    delivery.deliver = AsyncMock()
    executor = JobExecutor(
        store=store,
        delivery=delivery,
        config=config,
    )
    return executor, store, delivery


def store_holds(store: AsyncMock, job: CronJob) -> None:
    """The store holds the job under test, as it holds a dispatched job in production.

    ``make_executor`` answers ``get_job`` with a stock job for any id; tests whose outcome depends on the job's own
    fields (monitor config, schedule kind, failure count) must have the store hold that job instead.
    """
    store.get_job = AsyncMock(side_effect=lambda job_id: job if job_id == job.id else None)
