"""The maintenance scheduler registers the instance backup check and delays its heavy jobs past the boot burst."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.lifecycle import schedulers
from tests.support.recording_scheduler import RecordingScheduler


async def test_the_hourly_backup_check_is_registered_a_few_minutes_after_boot(maintenance_schedules: RecordingScheduler) -> None:
    before = maintenance_schedules.created_at

    func, trigger = maintenance_schedules.registered["instance_auto_backup"]
    assert func is schedulers._instance_auto_backup_job
    assert trigger.minutes == 60
    assert before + timedelta(minutes=4) < trigger.start_time < before + timedelta(minutes=6)
    assert {"db_maintenance", "incognito_cleanup"} <= maintenance_schedules.registered.keys()  # the neighbours are untouched


async def test_the_first_database_maintenance_pass_waits_past_the_first_screen(maintenance_schedules: RecordingScheduler) -> None:
    before = maintenance_schedules.created_at

    func, trigger = maintenance_schedules.registered["db_maintenance"]
    assert func is schedulers._db_maintenance_job
    assert trigger.hours == 6
    assert before + timedelta(minutes=2) < trigger.start_time < before + timedelta(minutes=4)


async def test_the_job_delegates_to_the_service_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    tick = AsyncMock()
    monkeypatch.setattr("app.services.instance_archive.auto_backup.run_auto_backup_tick", tick)

    await schedulers._instance_auto_backup_job()

    tick.assert_awaited_once()
