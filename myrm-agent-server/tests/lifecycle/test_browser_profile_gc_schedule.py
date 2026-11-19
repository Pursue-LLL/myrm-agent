"""The browser profile GC is registered on the maintenance scheduler, delayed past startup, and prunes for real off the event loop."""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from myrm_agent_harness.toolkits.browser.doctor.profiles import ProfileCleanupResult

from app.lifecycle import schedulers
from tests.support.recording_scheduler import RecordingScheduler

_JOB_ID = "browser_profile_gc"
_PRUNE = "myrm_agent_harness.toolkits.browser.cleanup_stale_browser_profiles"


async def test_the_gc_runs_every_six_hours_starting_after_the_boot_burst(maintenance_schedules: RecordingScheduler) -> None:
    before = maintenance_schedules.created_at

    func, trigger = maintenance_schedules.registered[_JOB_ID]
    assert func is schedulers._browser_profile_gc_job
    assert trigger.hours == 6
    assert before + timedelta(minutes=14) < trigger.start_time < before + timedelta(minutes=16)
    neighbours = {"db_maintenance", "incognito_cleanup", "checkpoint_history_prune", "instance_auto_backup"}
    assert neighbours <= maintenance_schedules.registered.keys()  # the other jobs are untouched


async def test_the_job_prunes_for_real_with_the_default_age_guard_and_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict[str, object], int]] = []

    def prune(**kwargs: object) -> ProfileCleanupResult:
        calls.append((kwargs, threading.get_ident()))
        return {"pruned": 0, "reclaimed_bytes": 0, "dry_run": False, "failed": []}

    monkeypatch.setattr(_PRUNE, prune)

    await schedulers._browser_profile_gc_job()

    [(kwargs, thread)] = calls
    assert kwargs == {"dry_run": False}  # a real prune that keeps the library's 24 h age guard
    assert thread != threading.get_ident()  # the directory walk and the process-table read must not block the event loop


async def test_a_failing_prune_is_logged_and_does_not_escape(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def prune(**kwargs: object) -> ProfileCleanupResult:
        raise OSError("temp directory unreadable")

    monkeypatch.setattr(_PRUNE, prune)

    await schedulers._browser_profile_gc_job()

    assert "Browser profile GC failed: temp directory unreadable" in caplog.text
