"""A `CronManager` over a mocked store and scheduler, and the job builders its unit tests share.

[INPUT]
- toolkits.cron.manager::CronManager (POS: the CRUD and state-change facade under test)
- toolkits.cron.types::CronJob, JobStatus, JobType, Schedule, ScheduleKind (POS: the job model the builders fill in)

[OUTPUT]
- make_schedule: a schedule of the given kind and expression (hourly cron by default)
- make_job: an active agent job with a prompt and no delivery; any field can be overridden
- make_manager: a `CronManager` over an `AsyncMock` store (lists and counts come back empty, `save_job` returns the job
  it is given, a test sets what `get_job` answers) and a `MagicMock` scheduler; a test reaches both mocks as
  `manager._store` and `manager._scheduler`

[POS]
Pytest-only helper shared by the `CronManager` unit tests (creation, update, queries and state changes): a test states
the job and pins the store and scheduler calls the manager makes. `cron_manager_stack` is the counterpart over a real
`InMemoryCronStore`, for tests that read the outcome from the store instead.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus, JobType, Schedule, ScheduleKind

# Tests override any job field by name, so the constructor is called through a variadic callable: a
# `**dict[str, object]` expansion is checked against every field type and rejected.
_new_job: Callable[..., CronJob] = CronJob


def make_schedule(kind: ScheduleKind = ScheduleKind.CRON, expr: str = "0 * * * *") -> Schedule:
    return Schedule(kind=kind, expr=expr)


def make_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "job-1",
        "name": "Test Job",
        "job_type": JobType.AGENT,
        "schedule": make_schedule(),
        "status": JobStatus.ACTIVE,
        "prompt": "test prompt",
    }
    defaults.update(overrides)
    return _new_job(**defaults)


def make_manager(*, shell_enabled: bool = True) -> CronManager:
    store = AsyncMock()
    store.save_job = AsyncMock(side_effect=lambda j: j)
    store.get_job = AsyncMock()
    store.get_monitor_state = AsyncMock(return_value=None)
    store.delete_job_cascade = AsyncMock(return_value=True)
    store.save_monitor_state = AsyncMock()
    store.delete_monitor_state = AsyncMock()
    store.list_jobs = AsyncMock(return_value=[])
    store.count_jobs = AsyncMock(return_value=0)
    store.list_runs = AsyncMock(return_value=[])
    store.count_runs = AsyncMock(return_value=0)
    store.batch_get_monitor_states = AsyncMock(return_value={})
    scheduler = MagicMock()
    scheduler.notify_change = MagicMock()
    return CronManager(store=store, scheduler=scheduler, shell_enabled=shell_enabled)
