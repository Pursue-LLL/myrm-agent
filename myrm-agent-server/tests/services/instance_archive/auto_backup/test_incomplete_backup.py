"""A scheduled backup that left something unreadable behind is a failure, kept as a salvage copy beside the real ones."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from myrm_agent_harness.infra.state_archive import read_manifest

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.instance_archive import export_service
from app.services.instance_archive.auto_backup.models import AutoBackupState
from app.services.instance_archive.policy import StateScan
from tests.services.instance_archive.archive_flow import stage_archive
from tests.services.instance_archive.auto_backup.rig import Rig, build_rig
from tests.services.instance_archive.conftest import PERMISSIONS_ENFORCED


def _leave_out(monkeypatch: pytest.MonkeyPatch, *paths: str) -> None:
    """Make every export report ``paths`` as carried yet unreadable."""
    real_scan = export_service.scan_state_dir

    def scan(state_dir: Path) -> StateScan:
        found = real_scan(state_dir)
        return replace(found, unreadable=[*found.unreadable, *paths])

    monkeypatch.setattr(export_service, "scan_state_dir", scan)


def _salvage(rig: Rig) -> list[Path]:
    return sorted(rig.default_folder.glob("*.incomplete.zip"))


def test_an_incomplete_export_is_a_recorded_failure_and_leaves_a_restorable_salvage_copy(
    source_state: Path, target_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state)
    _leave_out(monkeypatch, "wiki/private")

    state = rig.runner.run()

    assert state.last_error_code == "backup_incomplete"
    assert state.consecutive_failures == 1
    assert rig.store.load()[1] == state
    assert rig.stored() == []  # nothing here counts as a complete backup
    [salvage] = _salvage(rig)
    assert "wiki/page.md" in {entry.path for entry in read_manifest(salvage).entries}
    assert not list(rig.default_folder.glob("*.partial"))
    assert not list(rig.paths.exports.glob("*"))
    report, *_ = stage_archive(target_state, salvage, user_id=LOCAL_USER_ID, passphrase=None)  # restores like any backup
    assert not report.identity_dropped


def test_incomplete_runs_never_prune_complete_backups_and_keep_only_the_newest_salvage(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state)
    rig.configure(keep=1)
    rig.runner.run()
    [complete] = rig.stored()
    _leave_out(monkeypatch, "wiki/private")

    for _ in range(3):
        rig.clock.advance(days=1)
        rig.runner.run()

    assert rig.stored() == [complete]
    assert len(_salvage(rig)) == 1
    assert _salvage(rig)[0].name.startswith("myrm-auto-backup-") and "20261016" in _salvage(rig)[0].name


def test_the_second_incomplete_run_in_a_row_alerts_once(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = build_rig(source_state)
    _leave_out(monkeypatch, "wiki/private")

    rig.runner.run()
    assert rig.alerts == []
    rig.clock.advance(minutes=31)
    rig.runner.run()
    rig.clock.advance(minutes=31)
    rig.runner.run()

    assert rig.alerts == ["backup_incomplete"]


def test_a_complete_run_clears_the_failure_and_the_salvage_copy_it_supersedes(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = build_rig(source_state)
    with monkeypatch.context() as patched:
        _leave_out(patched, "wiki/private")
        rig.runner.run()
    assert len(_salvage(rig)) == 1
    rig.clock.advance(minutes=31)

    state = rig.runner.run()

    assert state == AutoBackupState(last_attempt_at=rig.clock.now)
    assert len(rig.stored()) == 1
    assert _salvage(rig) == []


@pytest.mark.skipif(not PERMISSIONS_ENFORCED, reason="needs POSIX permissions that apply to the current user")
def test_a_file_the_app_cannot_open_makes_the_scheduled_backup_incomplete(source_state: Path) -> None:
    locked = source_state / "wiki" / "locked.md"
    locked.write_text("cannot be opened")
    locked.chmod(0)
    rig = build_rig(source_state)
    try:
        state = rig.runner.run()
    finally:
        locked.chmod(0o600)

    assert state.last_error_code == "backup_incomplete"
    assert rig.stored() == []
    [salvage] = _salvage(rig)
    assert "wiki/locked.md" not in {entry.path for entry in read_manifest(salvage).entries}
