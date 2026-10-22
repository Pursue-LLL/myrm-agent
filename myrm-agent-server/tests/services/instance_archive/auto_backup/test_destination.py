"""Where backups may be written: outside live data, or under the excluded local-history tree."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from app.services.instance_archive.auto_backup import destination
from app.services.instance_archive.auto_backup.destination import (
    destination_path,
    prepare_destination,
    prepare_destination_guarded,
)
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard
from app.services.instance_archive.auto_backup.models import AutoBackupError
from app.services.instance_archive.models import ArchivePaths


@pytest.fixture
def paths(tmp_path: Path) -> ArchivePaths:
    state = tmp_path / "state"
    state.mkdir()
    return ArchivePaths(state)


def test_default_folder_is_created_under_the_excluded_backups_tree(paths: ArchivePaths) -> None:
    folder = prepare_destination(paths, None)

    assert folder == (paths.state_dir / "backups" / "instance").resolve()
    assert folder.is_dir()
    assert destination_path(paths, None) == paths.state_dir / "backups" / "instance"


def test_a_folder_outside_the_state_directory_is_created_and_accepted(paths: ArchivePaths, tmp_path: Path) -> None:
    target = tmp_path / "external" / "drive" / "backups"

    assert prepare_destination(paths, str(target)) == target.resolve()
    assert target.is_dir()


@pytest.mark.parametrize(
    "inside", ["", "wiki", "skills/demo", "instance_archive", "instance_archive/exports", "harness/workspace"]
)
def test_folders_inside_live_data_are_refused(paths: ArchivePaths, inside: str) -> None:
    target = paths.state_dir / inside

    with pytest.raises(AutoBackupError) as refused:
        prepare_destination(paths, str(target))

    assert refused.value.code == "backup_dir_inside_state"
    assert not (target / "myrm-auto-backup-x").exists()


def test_a_subfolder_of_local_history_is_accepted(paths: ArchivePaths) -> None:
    assert prepare_destination(paths, str(paths.state_dir / "backups" / "mine")).is_dir()


def test_a_symlink_into_live_data_is_refused_by_where_it_points(paths: ArchivePaths, tmp_path: Path) -> None:
    (paths.state_dir / "wiki").mkdir()
    link = tmp_path / "innocent-looking"
    link.symlink_to(paths.state_dir / "wiki", target_is_directory=True)

    with pytest.raises(AutoBackupError) as refused:
        prepare_destination(paths, str(link))

    assert refused.value.code == "backup_dir_inside_state"


def test_a_relative_path_is_refused(paths: ArchivePaths) -> None:
    with pytest.raises(AutoBackupError) as refused:
        prepare_destination(paths, "backups/here")

    assert refused.value.code == "backup_dir_invalid"


def test_a_leading_tilde_is_expanded_to_the_home_directory(
    paths: ArchivePaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert destination_path(paths, "~/Backups") == tmp_path / "Backups"


def test_a_home_that_cannot_be_determined_leaves_the_path_as_typed_and_is_refused_as_unusable(
    paths: ArchivePaths, unknown_home_dir: str
) -> None:
    assert destination_path(paths, unknown_home_dir) == Path(unknown_home_dir)

    with pytest.raises(AutoBackupError) as refused:
        prepare_destination(paths, unknown_home_dir)

    assert refused.value.code == "backup_dir_invalid"


def test_a_file_in_the_way_is_refused(paths: ArchivePaths, tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x")

    with pytest.raises(AutoBackupError) as refused:
        prepare_destination(paths, str(blocker))

    assert refused.value.code == "backup_dir_invalid"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="permission bits are not enforced here")
def test_a_read_only_folder_is_refused(paths: ArchivePaths, tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(AutoBackupError) as refused:
            prepare_destination(paths, str(locked))
    finally:
        locked.chmod(0o700)

    assert refused.value.code == "backup_dir_not_writable"
    assert not list(locked.iterdir())


def test_a_folder_that_does_not_answer_is_refused_as_unavailable(paths: ArchivePaths, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = threading.Event()

    def hung(*_: object) -> Path:
        answers.wait()
        return paths.state_dir

    monkeypatch.setattr(destination, "prepare_destination", hung)
    try:
        with pytest.raises(AutoBackupError) as refused:
            prepare_destination_guarded(FolderGuard(0.2), paths, None)
    finally:
        answers.set()

    assert refused.value.code == "backup_write_failed"


def test_the_guarded_preparation_gives_the_same_folder_and_the_same_refusals_as_the_plain_one(
    paths: ArchivePaths, tmp_path: Path
) -> None:
    guard = FolderGuard()
    target = tmp_path / "external"

    assert prepare_destination_guarded(guard, paths, str(target)) == prepare_destination(paths, str(target))
    with pytest.raises(AutoBackupError) as refused:
        prepare_destination_guarded(guard, paths, "backups/here")

    assert refused.value.code == "backup_dir_invalid"
