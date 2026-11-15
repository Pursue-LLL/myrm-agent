"""Lifecycle test support.

The cognitive-clock singletons are process-global, so every test starts from fresh ones; ``maintenance_schedules`` boots
the real maintenance scheduler on a recording double.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from myrm_agent_harness.runtime.cognitive_clock.signals import get_global_pause_signal

from app.lifecycle import schedulers
from app.lifecycle.cognitive_clock import activity_sensor, wakeup_guard
from tests.support.recording_scheduler import RecordingScheduler


@pytest.fixture(autouse=True)
def _fresh_cognitive_clock_singletons(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A grace period or recorded activity left by one test must not suppress the next one."""
    monkeypatch.setattr(wakeup_guard, "_GLOBAL_WAKEUP_GUARD", None)
    monkeypatch.setattr(activity_sensor, "_GLOBAL_ACTIVITY_SENSOR", None)
    pause_signal = get_global_pause_signal()
    pause_signal.clear()
    yield
    pause_signal.clear()


@pytest.fixture
async def maintenance_schedules(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[RecordingScheduler]:
    """Boot the real maintenance scheduler on a recording double and wait until it has been started.

    APScheduler 4 runs schedules only after an explicit start, so a boot that registers without starting fails here
    instead of leaving every job dead; once the wait returns, every registration of the boot is visible.
    """
    scheduler = RecordingScheduler()
    monkeypatch.setattr("apscheduler.AsyncScheduler", lambda: scheduler)
    monkeypatch.setattr(schedulers.maintenance, "_db_maintenance_scheduler", None)
    monkeypatch.setattr(schedulers.maintenance, "_db_maintenance_scheduler_task", None)
    await schedulers.start_db_maintenance_scheduler()
    try:
        await asyncio.wait_for(scheduler.started.wait(), timeout=10)
        yield scheduler
    finally:
        await schedulers.stop_db_maintenance_scheduler()
