"""The service the API and the scheduler drive: settings, background runs, alerts, availability."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.event.app_event_bus import AppEventType, get_event_bus
from app.services.instance_archive import ArchivePaths, ExportBusyError, export_jobs
from app.services.instance_archive.auto_backup import (
    ALERT_COMPONENT,
    AutoBackupError,
    AutoBackupSettings,
    get_auto_backup_service,
    run_auto_backup_tick,
)
from app.services.instance_archive.auto_backup import service as service_module
from tests.services.instance_archive.auto_backup.harness import ON, Harness


async def test_a_fresh_instance_is_off_and_shows_the_default_folder(harness: Harness) -> None:
    view = await harness.service.get_view()

    assert view.settings == AutoBackupSettings()
    assert view.directory == harness.paths.state_dir / "backups" / "instance"
    assert (view.backups, view.running, view.overdue) == ((), False, False)


async def test_turning_it_on_makes_the_first_backup_right_away(harness: Harness) -> None:
    view = await harness.service.apply(ON)
    assert view.settings.enabled

    await harness.settled()

    final = harness.service.view()
    assert final.last is not None and final.last.created_at == harness.clock.now
    assert [b.name for b in final.backups] == [final.last.name]


async def test_an_unusable_folder_is_rejected_and_nothing_is_saved(harness: Harness) -> None:
    with pytest.raises(AutoBackupError) as refused:
        await harness.service.apply(replace(ON, directory=str(harness.paths.state_dir / "skills")))

    assert refused.value.code == "backup_dir_inside_state"
    assert harness.service.view().settings.enabled is False


async def test_turning_it_off_starts_nothing(harness: Harness) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    before = harness.service.view().state

    harness.clock.advance(days=3)
    view = await harness.service.apply(replace(ON, enabled=False))

    assert view.settings.enabled is False
    assert not harness.service.view().running
    assert harness.service.view().state == before


async def test_changing_the_folder_clears_the_failure_back_off(harness: Harness, tmp_path: Path) -> None:
    store = harness.service._store
    store.save_settings(replace(ON, directory=str(harness.paths.state_dir / "wiki")))
    harness.clock.advance(hours=1)
    assert await harness.service.tick()
    await harness.settled()
    assert store.load()[1].consecutive_failures == 1

    await harness.service.apply(replace(ON, directory=str(tmp_path / "usb")))
    await harness.settled()

    state = store.load()[1]
    assert state.consecutive_failures == 0 and state.last_error_code is None
    assert len(harness.stored(tmp_path / "usb")) == 1


async def test_a_new_folder_gets_its_first_backup_at_once_even_when_the_last_one_is_recent(
    harness: Harness, tmp_path: Path
) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    harness.clock.advance(hours=1)  # by the clock nothing is due

    await harness.service.apply(replace(ON, directory=str(tmp_path / "usb")))
    await harness.settled()

    view = harness.service.view()
    assert view.last is not None and view.last.created_at == harness.clock.now
    assert harness.stored(tmp_path / "usb") == [view.last.name]


async def test_a_folder_chosen_while_off_is_backed_up_to_when_turned_on(harness: Harness, tmp_path: Path) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    harness.clock.advance(hours=1)
    usb = replace(ON, directory=str(tmp_path / "usb"))

    await harness.service.apply(replace(usb, enabled=False))
    assert harness.service.view().last is None  # nothing was ever backed up there
    await harness.service.apply(usb)
    await harness.settled()

    assert len(harness.stored(tmp_path / "usb")) == 1


async def test_naming_the_default_folder_explicitly_is_not_a_change(harness: Harness) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    before = harness.service.view().state
    harness.clock.advance(hours=1)

    await harness.service.apply(replace(ON, directory=str(harness.paths.state_dir / "backups" / "instance")))

    assert harness.service.view().state == before
    assert not harness.service.view().running


async def test_tick_starts_a_backup_only_when_one_is_due(harness: Harness) -> None:
    assert not await harness.service.tick()  # off

    await harness.service.apply(ON)
    await harness.settled()
    harness.clock.advance(hours=5)
    assert not await harness.service.tick()  # a backup completed a few hours ago

    harness.clock.advance(hours=20)
    assert await harness.service.tick()
    await harness.settled()
    assert len(harness.service.view().backups) == 2


async def test_backups_deleted_by_hand_make_the_next_tick_back_up_at_once(harness: Harness) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    harness.clock.advance(hours=1)
    assert not await harness.service.tick()  # a backup completed an hour ago

    folder = harness.service.view().directory
    for name in harness.stored(folder):
        (folder / name).unlink()
    view = harness.service.view()
    assert view.last is None and view.backups == () and not view.overdue

    assert await harness.service.tick()  # the folder, not a record, says there is nothing to protect the data
    await harness.settled()
    assert len(harness.service.view().backups) == 1


async def test_a_folder_that_already_holds_a_recent_backup_is_not_backed_up_again_when_selected(
    harness: Harness, tmp_path: Path
) -> None:
    usb = tmp_path / "usb"
    harness.put(usb, harness.clock.now - timedelta(hours=2))

    view = await harness.service.apply(replace(ON, directory=str(usb)))

    assert not view.running
    assert view.last is not None and view.last.created_at == harness.clock.now - timedelta(hours=2)
    assert len(harness.stored(usb)) == 1


async def test_another_instances_recent_backup_in_a_shared_folder_does_not_count_as_ours(
    harness: Harness, tmp_path: Path
) -> None:
    shared = tmp_path / "synced-drive"
    theirs = harness.put(shared, harness.clock.now - timedelta(minutes=5), tag="b07e5a44")

    view = await harness.service.apply(replace(ON, directory=str(shared)))
    assert view.last is None and view.backups == ()  # their file is invisible to us
    await harness.settled()

    assert len(harness.stored(shared)) == 1 and theirs.exists()  # we backed up on our own account


async def test_a_file_dated_in_the_future_neither_hides_the_real_backups_nor_triggers_hourly_ones(
    harness: Harness,
) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    folder = harness.service.view().directory
    ahead = harness.put(folder, harness.clock.now + timedelta(days=400))  # made while the clock ran ahead

    view = harness.service.view()
    assert view.last is not None and view.last.created_at == harness.clock.now  # the future file is not "the last"
    assert len(view.backups) == 2

    harness.clock.advance(hours=3)
    assert not await harness.service.tick()  # one backup a day, not one every tick, however far ahead the file is
    harness.clock.advance(hours=22)
    assert await harness.service.tick()
    await harness.settled()
    assert ahead.exists()  # it is not ours to guess that it is garbage


async def test_a_failure_stamped_by_a_clock_that_ran_ahead_does_not_stop_the_retries(harness: Harness) -> None:
    harness.service._store.save_settings(replace(ON, directory=str(harness.paths.state_dir / "wiki")))
    harness.clock.advance(days=3)  # the clock runs ahead, and the attempt made then fails
    assert await harness.service.tick()
    await harness.settled(attempts=1)
    stamped = harness.service.view().state.last_attempt_at

    harness.clock.advance(days=-3)  # the clock is corrected, and the folder with it
    harness.service._store.save_settings(ON)
    harness.clock.advance(hours=1)
    assert stamped is not None and stamped > harness.clock.now
    assert harness.service.view().due

    assert await harness.service.tick()
    await harness.settled()
    view = harness.service.view()
    assert view.last is not None and view.last.created_at == harness.clock.now
    assert (view.state.consecutive_failures, view.state.last_error_code) == (0, None)


async def test_tick_and_run_now_leave_a_running_export_alone(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    harness.service._store.save_settings(ON)
    gate = threading.Event()
    real = export_jobs.build_export

    def slow(**kwargs: object):
        gate.wait(30)
        return real(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(export_jobs, "build_export", slow)
    manual = harness.service._manager.start(
        user_id="local-user", app_version="1", deploy_mode="local", config_key=None, passphrase=None
    )

    try:
        assert not await harness.service.tick()
        with pytest.raises(ExportBusyError):
            await harness.service.start_run()
    finally:
        gate.set()
        manual.done.wait(30)
        harness.service._manager.discard(manual.job_id)


@pytest.mark.parametrize("callers", [("start_run", "start_run"), ("start_run", "tick"), ("tick", "tick")])
async def test_two_callers_that_both_passed_their_checks_start_one_backup(harness: Harness, callers: tuple[str, str]) -> None:
    harness.service._store.save_settings(ON)
    gate = threading.Event()
    started: list[str] = []

    class Blocked:
        def run(self) -> None:
            started.append("run")
            gate.wait(30)

    harness.service._runner = Blocked()  # type: ignore[assignment]
    meeting = threading.Barrier(2)  # both checks finish before either caller claims the run
    for name in ("_check_can_run", "_due_and_idle"):
        check = getattr(harness.service, name)

        def meet(check: Callable[[], object] = check) -> object:
            result = check()
            meeting.wait(10)
            return result

        setattr(harness.service, name, meet)

    try:
        outcomes = await asyncio.gather(*(getattr(harness.service, caller)() for caller in callers), return_exceptions=True)
        # start_run answers None when it started and raises when refused; tick answers whether it started
        assert [outcome is None or outcome is True for outcome in outcomes].count(True) == 1
        assert harness.service.view().running
    finally:
        gate.set()
        while harness.service.view().running:
            await asyncio.sleep(0.01)
    assert started == ["run"]


async def test_run_now_works_even_when_the_schedule_is_off_and_rejects_a_bad_folder(harness: Harness, tmp_path: Path) -> None:
    await harness.service.start_run()
    await harness.settled()
    last = harness.service.view().last
    assert last is not None and last.created_at == harness.clock.now

    harness.service._store.save_settings(replace(ON, directory=str(harness.paths.state_dir / "wiki")))
    with pytest.raises(AutoBackupError):
        await harness.service.start_run()


async def test_repeated_failures_alert_once_on_the_event_loop(harness: Harness) -> None:
    harness.service._store.save_settings(replace(ON, directory=str(harness.paths.state_dir / "wiki")))
    main_thread = threading.current_thread().name

    for expected in (1, 2, 3):
        harness.clock.advance(hours=2)
        assert await harness.service.tick()
        await harness.settled(attempts=expected)

    assert harness.alerts == [("backup_dir_inside_state", main_thread)]


@pytest.fixture
def isolated_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service_module, "_services", {})
    monkeypatch.setattr(export_jobs, "_managers", {})


def _env(monkeypatch: pytest.MonkeyPatch, state: Path, *, sandbox: bool = False, sqlite: Path | None = None) -> None:
    settings = SimpleNamespace(
        database=SimpleNamespace(state_dir=str(state), sqlite_path=str(sqlite or state / "data.db")),
        app_version="1.0.0",
    )
    monkeypatch.setattr(service_module, "get_settings", lambda: settings)
    monkeypatch.setattr(service_module, "is_sandbox", lambda: sandbox)


def test_the_service_is_shared_per_instance_and_uses_the_shared_export_manager(
    source_state: Path, monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    _env(monkeypatch, source_state)

    first, second = get_auto_backup_service(), get_auto_backup_service()

    assert first is not None and first is second
    assert first._manager is export_jobs.get_export_manager(ArchivePaths(source_state))


def test_it_is_not_offered_in_a_cloud_sandbox_or_for_a_nonstandard_layout(
    source_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    _env(monkeypatch, source_state, sandbox=True)
    assert get_auto_backup_service() is None

    _env(monkeypatch, source_state, sqlite=tmp_path / "elsewhere" / "data.db")
    assert get_auto_backup_service() is None


async def test_a_scheduler_tick_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(service_module, "get_auto_backup_service", boom)

    await run_auto_backup_tick()


async def test_a_scheduler_tick_is_a_noop_where_the_service_is_not_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "get_auto_backup_service", lambda: None)

    await run_auto_backup_tick()


def test_the_failure_alert_is_a_health_alert_the_ui_can_recognise() -> None:
    bus = get_event_bus()
    queue = bus.subscribe()
    try:
        service_module.publish_failure_alert("insufficient_space")
        event = queue.get_nowait()
    finally:
        bus.unsubscribe(queue)

    assert event.event_type is AppEventType.HEALTH_ALERT
    assert event.data["component"] == ALERT_COMPONENT == "instance_backup"
    assert event.data["status"] == "fail" and event.data["code"] == "insufficient_space"
    assert event.data["message"] and event.data["fix_suggestion"]
