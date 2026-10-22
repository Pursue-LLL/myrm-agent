"""A backup folder that cannot be read is unknown, never taken for an empty one."""

from __future__ import annotations

import shutil
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.instance_archive.auto_backup import AutoBackupError
from app.services.instance_archive.auto_backup import service as service_module
from tests.services.instance_archive.auto_backup.harness import ON, Harness


def _unplug(drive: Path) -> Path:
    """The drive goes away and a plain file takes its mount point, so nothing below it can be read or created."""
    away = drive.with_name(drive.name + ".away")
    drive.rename(away)
    drive.write_text("")
    return away


def _replug(drive: Path, away: Path) -> None:
    drive.unlink()
    away.rename(drive)


async def test_taking_the_drive_away_after_a_backup_is_no_failure_until_the_next_one_is_due(
    harness: Harness, tmp_path: Path
) -> None:
    drive = tmp_path / "USB"
    await harness.service.apply(replace(ON, directory=str(drive / "Backups")))
    await harness.settled()
    first = harness.service.view().last
    assert first is not None and harness.service.view().reachable

    away = _unplug(drive)
    for _ in range(20):  # the app keeps ticking every hour
        harness.clock.advance(hours=1)
        assert not await harness.service.tick()
    view = harness.service.view()
    assert (view.reachable, view.last, view.backups) == (False, None, ())
    assert (view.due, view.overdue, view.state.consecutive_failures, harness.alerts) == (False, False, 0, [])

    main_thread = threading.current_thread().name
    harness.clock.advance(hours=4)  # a full day since the backup: the attempt is due now, and fails
    assert await harness.service.tick()
    await harness.settled(attempts=1)
    assert harness.alerts == []
    assert harness.service.view().overdue

    harness.clock.advance(hours=2)
    assert await harness.service.tick()
    await harness.settled(attempts=2)
    assert harness.alerts == [("backup_dir_invalid", main_thread)]

    _replug(drive, away)
    harness.clock.advance(hours=1)  # past the quick-retry gap
    view = harness.service.view()
    assert view.reachable and view.last == first and view.due  # the earlier backup is still there, and old enough
    assert await harness.service.tick()
    await harness.settled()
    view = harness.service.view()
    assert view.last is not None and view.last.created_at == harness.clock.now
    assert (view.state.consecutive_failures, view.state.last_error_code, len(harness.alerts)) == (0, None, 1)


async def test_a_deleted_backup_folder_is_unreachable_until_the_next_backup_recreates_it(harness: Harness) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    folder = harness.service.view().directory
    shutil.rmtree(folder)

    view = harness.service.view()
    assert (view.reachable, view.last, view.due) == (False, None, False)

    harness.clock.advance(hours=25)
    assert await harness.service.tick()
    await harness.settled()
    view = harness.service.view()
    assert view.reachable and view.last is not None and view.last.created_at == harness.clock.now


async def test_a_folder_that_denies_access_is_unreachable_not_empty(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    await harness.service.apply(ON)
    await harness.settled()

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("access denied")

    monkeypatch.setattr(service_module, "list_backups", denied)
    harness.clock.advance(hours=2)

    view = harness.service.view()
    assert (view.reachable, view.last, view.backups, view.due, view.overdue) == (False, None, (), False, False)
    assert not await harness.service.tick()


async def test_an_emptied_but_readable_folder_is_reachable_and_due(harness: Harness) -> None:
    await harness.service.apply(ON)
    await harness.settled()
    folder = harness.service.view().directory
    for name in harness.stored(folder):
        (folder / name).unlink()

    view = harness.service.view()
    assert (view.reachable, view.last, view.due) == (True, None, True)


async def test_a_folder_under_an_unknown_home_is_unavailable_and_can_be_corrected(
    harness: Harness, tmp_path: Path, unknown_home_dir: str
) -> None:
    off = replace(ON, enabled=False, directory=unknown_home_dir)

    view = await harness.service.apply(off)  # a mistyped folder must not make the settings unreadable
    assert (view.settings.directory, view.directory, view.reachable) == (unknown_home_dir, Path(unknown_home_dir), False)

    with pytest.raises(AutoBackupError) as refused:
        await harness.service.apply(replace(off, enabled=True))
    assert refused.value.code == "backup_dir_invalid"
    assert not (await harness.service.get_view()).settings.enabled

    folder = tmp_path / "Backups"
    await harness.service.apply(replace(ON, directory=str(folder)))
    await harness.settled()
    view = await harness.service.get_view()
    assert (view.directory, view.reachable) == (folder, True) and view.last is not None


async def test_a_scheduled_backup_whose_home_is_gone_is_a_recorded_failure_not_a_crash(
    harness: Harness, unknown_home_dir: str
) -> None:
    harness.service._store.save_settings(replace(ON, directory=unknown_home_dir))  # saved while that home still existed

    assert await harness.service.tick()
    await harness.settled()

    state = harness.service.view().state
    assert (state.consecutive_failures, state.last_error_code) == (1, "backup_dir_invalid")
