"""The checkpoint-history prune is registered on the maintenance scheduler, delayed past startup."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.lifecycle import schedulers
from tests.support.recording_scheduler import RecordingScheduler

_JOB_ID = "checkpoint_history_prune"


async def test_the_prune_runs_every_six_hours_starting_after_the_boot_burst(maintenance_schedules: RecordingScheduler) -> None:
    before = maintenance_schedules.created_at

    func, trigger = maintenance_schedules.registered[_JOB_ID]
    assert func is schedulers._checkpoint_history_prune_job
    assert trigger.hours == 6
    assert before + timedelta(minutes=9) < trigger.start_time < before + timedelta(minutes=11)
    assert {"db_maintenance", "incognito_cleanup"} <= maintenance_schedules.registered.keys()  # the neighbours are untouched


async def test_the_job_delegates_to_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    prune = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.system.checkpoint_history_service.run_checkpoint_history_prune", prune)

    await schedulers._checkpoint_history_prune_job()

    prune.assert_awaited_once()
