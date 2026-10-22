"""One scheduled backup end to end over a real state directory and the real export pipeline."""

from __future__ import annotations

import os
import shutil
import threading
import time
import zipfile
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from myrm_agent_harness.infra.state_archive import ArchiveErrorCode, ArchiveVerificationError, read_manifest

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.instance_archive import ArchivePaths, ExportBusyError, ExportJobManager, export_jobs, run_pending_promotion
from app.services.instance_archive.auto_backup import runner as runner_module
from app.services.instance_archive.auto_backup.models import AutoBackupState
from app.services.instance_archive.auto_backup.retention import backup_name
from tests.services.instance_archive.archive_flow import (
    export_archive,
    make_importer,
    query_rows,
    stage_archive,
    upload_archive,
)
from tests.services.instance_archive.auto_backup.rig import build_rig


def test_a_completed_backup_is_a_readable_archive_written_for_the_local_identity(source_state: Path) -> None:
    rig = build_rig(source_state)

    state = rig.runner.run()

    [name] = rig.stored()
    final = rig.default_folder / name
    manifest = read_manifest(final)
    assert manifest.metadata["source_user_id"] == LOCAL_USER_ID
    assert manifest.metadata["deploy_mode"] == "local"
    assert name == backup_name(rig.clock.now, rig.store.tag())
    assert state == AutoBackupState(last_attempt_at=rig.clock.now)  # success is the file, not a record
    assert rig.store.load()[1] == state
    assert not list(rig.paths.exports.glob("*"))
    assert not list(rig.default_folder.glob("*.partial"))


def test_a_scheduled_backup_restores_with_the_identity_a_local_manual_import_uses(source_state: Path, target_state: Path) -> None:
    rig = build_rig(source_state)
    rig.runner.run()
    archive = rig.default_folder / rig.stored()[0]

    local_report, *_ = stage_archive(target_state, archive, user_id=LOCAL_USER_ID, passphrase=None)
    stranger_report, *_ = stage_archive(target_state, archive, user_id="someone-else", passphrase=None)

    assert not local_report.identity_dropped
    assert stranger_report.identity_dropped


def test_a_scheduled_backup_carries_no_keys(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = build_rig(source_state)
    seen: dict[str, object] = {}
    real_start = rig.manager.start

    def spy(**kwargs: object):
        seen.update(kwargs)
        return real_start(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(rig.manager, "start", spy)

    rig.runner.run()

    assert seen["config_key"] is None and seen["passphrase"] is None
    assert seen["user_id"] == LOCAL_USER_ID


def test_the_newest_backups_are_kept_and_unrelated_files_are_not_touched(source_state: Path, tmp_path: Path) -> None:
    folder = tmp_path / "usb" / "myrm"
    rig = build_rig(source_state)
    rig.configure(keep=2, directory=str(folder))
    folder.mkdir(parents=True)
    manual = folder / "myrm-backup-202610010300.zip"
    manual.write_bytes(b"downloaded by hand")
    (folder / "photos.zip").write_bytes(b"x")

    names = []
    for _ in range(3):
        rig.runner.run()
        names.append(rig.stored(folder)[0])
        rig.clock.advance(days=1)

    assert rig.stored(folder) == [names[2], names[1]]
    assert manual.exists() and (folder / "photos.zip").exists()


def test_a_new_backup_does_not_contain_the_earlier_ones_or_the_archive_workspace(source_state: Path) -> None:
    rig = build_rig(source_state)
    rig.runner.run()
    rig.clock.advance(days=1)
    rig.runner.run()

    newest = rig.default_folder / rig.stored()[0]
    with zipfile.ZipFile(newest) as archive:
        members = archive.namelist()
    carried = [member.removeprefix("payload/") for member in members if member.startswith("payload/")]
    assert "data.db" in carried and "wiki/page.md" in carried  # the check below is not vacuous
    assert not [path for path in carried if path.startswith(("backups/", "instance_archive/"))]


def test_retained_backups_survive_the_exports_sweep_of_later_runs(source_state: Path) -> None:
    rig = build_rig(source_state)
    rig.runner.run()
    first = rig.default_folder / rig.stored()[0]
    long_ago = time.time() - 30 * 24 * 3600
    os.utime(first, (long_ago, long_ago))
    rig.clock.advance(days=1)

    rig.runner.run()

    assert first.exists()
    assert len(rig.stored()) == 2


def test_retained_backups_and_the_schedule_survive_a_restore(
    source_state: Path, target_state: Path, dead_requester: Callable[[Path], None], tmp_path: Path
) -> None:
    rig = build_rig(target_state)
    rig.configure(keep=5)
    rig.runner.run()
    retained, tag = rig.stored(), rig.store.tag()
    source_archive = tmp_path / "from-elsewhere.zip"
    export_archive(source_state, source_archive, passphrase=None)
    importer, store, _ = make_importer(target_state, user_id=LOCAL_USER_ID)
    session_id = upload_archive(store, source_archive)
    importer.stage(session_id, passphrase=None, skip_secrets=False)
    importer.confirm(session_id, acknowledge_executables=True)
    dead_requester(target_state)

    outcome = run_pending_promotion(target_state, wait_seconds=0)

    assert outcome is not None and outcome.status.value == "restored"
    assert query_rows(target_state / "data.db", "SELECT id FROM chats") == [("c1",)]  # the restore really replaced the data
    assert rig.stored() == retained
    assert rig.store.tag() == tag  # still the same instance after a restore: its backups stay its own
    settings, _ = rig.store.load()
    assert settings.enabled and settings.keep == 5


def test_an_unusable_destination_is_recorded_and_never_starts_an_export(source_state: Path) -> None:
    rig = build_rig(source_state)
    rig.configure(directory=str(source_state / "wiki"))

    state = rig.runner.run()

    assert (state.consecutive_failures, state.last_error_code) == (1, "backup_dir_inside_state")
    assert not rig.paths.exports.exists() or not list(rig.paths.exports.iterdir())
    assert not (source_state / "wiki" / "data.db").exists()


def test_a_failing_run_never_deletes_existing_backups(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = build_rig(source_state)
    rig.configure(keep=1)
    rig.runner.run()
    kept = rig.stored()
    rig.clock.advance(days=1)

    def broken(**_: object):
        raise OSError("disk exploded")

    monkeypatch.setattr(export_jobs, "build_export", broken)
    state = rig.runner.run()

    assert state.last_error_code == "export_failed" and state.consecutive_failures == 1
    assert rig.stored() == kept


def test_not_enough_space_is_reported_as_such(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.infra.state_archive import InsufficientSpaceError

    rig = build_rig(source_state)

    def full(**_: object):
        raise InsufficientSpaceError(10, 1)

    monkeypatch.setattr(export_jobs, "build_export", full)

    assert rig.runner.run().last_error_code == "insufficient_space"


def test_the_user_is_alerted_once_when_failures_repeat_and_success_resets_the_count(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state)
    rig.configure(directory=str(source_state / "wiki"))

    states = [rig.runner.run() for _ in range(4)]

    assert [s.consecutive_failures for s in states] == [1, 2, 3, 4]
    assert rig.alerts == ["backup_dir_inside_state"]  # exactly at the second failure, not 1, 3 or 4

    rig.configure(directory=None)
    recovered = rig.runner.run()
    assert recovered.consecutive_failures == 0 and recovered.last_error_code is None
    rig.configure(directory=str(source_state / "wiki"))
    rig.runner.run()
    rig.runner.run()
    assert rig.alerts == ["backup_dir_inside_state"] * 2  # a new streak alerts again


def test_a_manual_export_in_flight_defers_the_run_without_recording_a_failure(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    real = export_jobs.build_export

    def slow(**kwargs: object):
        gate.wait(30)
        return real(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(export_jobs, "build_export", slow)
    manager = ExportJobManager(ArchivePaths(source_state))
    rig = build_rig(source_state, manager=manager)
    manual = manager.start(user_id="local-user", app_version="1", deploy_mode="local", config_key=None, passphrase=None)

    try:
        with pytest.raises(ExportBusyError):
            rig.runner.run()
        assert rig.store.load()[1].consecutive_failures == 0
        assert not rig.runner.running
    finally:
        gate.set()
        manual.done.wait(30)
        manager.discard(manual.job_id)


def test_across_volumes_the_backup_appears_only_when_complete_and_leaves_no_partial(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state)
    monkeypatch.setattr(runner_module, "_same_volume", lambda *_: False)
    seen_partials: list[bool] = []
    real_copy = shutil.copyfileobj

    def watching_copy(source, target, length=0):  # noqa: ANN001, ANN202
        real_copy(source, target, length)
        seen_partials.append(any(p.name.endswith(".zip.partial") for p in rig.default_folder.iterdir()))
        assert not rig.stored()  # no final name until the copy is whole

    monkeypatch.setattr(runner_module, "shutil", SimpleNamespace(copyfileobj=watching_copy))

    state = rig.runner.run()

    assert state.last_error_code is None and seen_partials == [True]
    assert len(rig.stored()) == 1
    assert not list(rig.default_folder.glob("*.partial"))
    assert not list(rig.paths.exports.glob("*"))


def test_an_interrupted_copy_leaves_neither_a_partial_nor_a_backup_name(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state)
    monkeypatch.setattr(runner_module, "_same_volume", lambda *_: False)

    def dying(*_: object, **__: object) -> None:
        raise OSError("device removed")

    monkeypatch.setattr(runner_module, "shutil", SimpleNamespace(copyfileobj=dying))

    state = rig.runner.run()

    assert state.last_error_code == "backup_write_failed"
    assert not list(rig.default_folder.iterdir())
    assert not list(rig.paths.exports.glob("*"))


def test_a_result_that_does_not_read_back_is_removed_and_reported(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = build_rig(source_state)

    def unreadable(_: Path):
        raise ArchiveVerificationError(ArchiveErrorCode.NOT_A_ZIP, "broken")

    monkeypatch.setattr(runner_module, "read_manifest", unreadable)

    state = rig.runner.run()

    assert state.last_error_code == "backup_unreadable"
    assert rig.stored() == []


def test_the_runner_reports_itself_running_only_while_it_runs(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gate, entered = threading.Event(), threading.Event()
    real = export_jobs.build_export

    def slow(**kwargs: object):
        entered.set()
        gate.wait(30)
        return real(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(export_jobs, "build_export", slow)
    rig = build_rig(source_state)
    worker = threading.Thread(target=rig.runner.run)

    assert not rig.runner.running
    worker.start()
    assert entered.wait(30)
    assert rig.runner.running
    with pytest.raises(ExportBusyError):
        rig.runner.run()
    gate.set()
    worker.join(60)
    assert not rig.runner.running


def test_instances_sharing_a_folder_each_keep_and_prune_only_their_own_backups(
    source_state: Path, target_state: Path, tmp_path: Path
) -> None:
    shared = tmp_path / "synced-drive"
    first, second = build_rig(source_state), build_rig(target_state)
    for rig in (first, second):
        rig.configure(keep=1, directory=str(shared))

    for _ in range(3):
        first.runner.run()
        second.runner.run()
        first.clock.advance(days=1)
        second.clock.advance(days=1)

    assert first.store.tag() != second.store.tag()
    assert len(first.stored(shared)) == len(second.stored(shared)) == 1  # each pruned down to its own newest
    assert len(list(shared.glob("*.zip"))) == 2  # and neither deleted the other's file


def test_a_failure_of_a_folder_that_is_no_longer_selected_is_not_charged_to_the_new_one(
    source_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, entered = threading.Event(), threading.Event()

    def dying_export(**_: object):
        entered.set()
        gate.wait(30)
        raise OSError("disk exploded")

    monkeypatch.setattr(export_jobs, "build_export", dying_export)
    rig = build_rig(source_state)
    outcome: list[AutoBackupState] = []
    worker = threading.Thread(target=lambda: outcome.append(rig.runner.run()))

    worker.start()
    assert entered.wait(30)
    rig.configure(directory=str(tmp_path / "usb"))  # the user points the backup elsewhere mid-run
    gate.set()
    worker.join(60)

    assert not worker.is_alive()
    assert outcome == [AutoBackupState()]
    assert rig.store.load()[1] == AutoBackupState()
    assert rig.alerts == []


def test_a_future_dated_file_does_not_evict_the_backup_a_run_just_wrote(source_state: Path) -> None:
    rig = build_rig(source_state)
    rig.configure(keep=1)
    rig.default_folder.mkdir(parents=True)
    ahead = rig.default_folder / backup_name(rig.clock.now + timedelta(days=400), rig.store.tag())
    ahead.write_bytes(b"written while the clock ran ahead")

    rig.runner.run()

    assert ahead.exists()
    assert backup_name(rig.clock.now, rig.store.tag()) in rig.stored()
