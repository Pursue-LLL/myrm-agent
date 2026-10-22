"""Retention only ever touches files this instance wrote."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

import pytest

from app.services.instance_archive.auto_backup.retention import (
    backup_name,
    incomplete_name,
    last_backup,
    list_backups,
    prune,
    prune_incomplete,
)

BASE = datetime(2026, 10, 1, 3, 0, 0, tzinfo=UTC)
TAG = "3fa9c2d1"
OTHER_TAG = "b07e5a44"


def _make(folder: Path, days: int, *, size: int = 10, tag: str = TAG) -> Path:
    path = folder / backup_name(BASE + timedelta(days=days), tag)
    path.write_bytes(b"x" * size)
    return path


def _names(folder: Path) -> list[str]:
    return [backup.name for backup in list_backups(folder, TAG)]


def test_name_carries_the_instance_tag_and_a_sortable_utc_stamp() -> None:
    local = datetime(2026, 10, 1, 11, 5, 9, tzinfo=timezone(timedelta(hours=8)))

    assert backup_name(local, TAG) == "myrm-auto-backup-3fa9c2d1-20261001-030509.zip"


def test_list_is_newest_first_with_sizes_and_moments(tmp_path: Path) -> None:
    _make(tmp_path, 0, size=1)
    _make(tmp_path, 2, size=3)
    _make(tmp_path, 1, size=2)

    listed = list_backups(tmp_path, TAG)

    assert [b.size_bytes for b in listed] == [3, 2, 1]
    assert listed[0].created_at == BASE + timedelta(days=2)


def test_foreign_files_are_never_listed(tmp_path: Path) -> None:
    mine = _make(tmp_path, 0)
    (tmp_path / "myrm-backup-202610010300.zip").write_bytes(b"manual download")
    (tmp_path / "holiday.zip").write_bytes(b"x")
    (tmp_path / f"myrm-auto-backup-{TAG}-20261001-030000.zip.bak").write_bytes(b"x")
    (tmp_path / f"myrm-auto-backup-{TAG}-2026-10-01.zip").write_bytes(b"x")
    (tmp_path / f"myrm-auto-backup-{TAG}-20269999-999999.zip").write_bytes(b"x")
    (tmp_path / "myrm-auto-backup-20261001-030000.zip").write_bytes(b"made without a tag")
    (tmp_path / f"myrm-auto-backup-{TAG}-20261002-030000.zip").mkdir()
    (tmp_path / f"myrm-auto-backup-{TAG}-20261003-030000.zip").symlink_to(mine)

    assert _names(tmp_path) == [mine.name]


def test_another_instances_backups_in_a_shared_folder_are_invisible(tmp_path: Path) -> None:
    mine = _make(tmp_path, 0)
    theirs = _make(tmp_path, 5, tag=OTHER_TAG)

    assert _names(tmp_path) == [mine.name]
    assert [b.name for b in list_backups(tmp_path, OTHER_TAG)] == [theirs.name]


def test_prune_keeps_the_newest_and_leaves_everything_else_alone(tmp_path: Path) -> None:
    oldest, middle, newest = _make(tmp_path, 0), _make(tmp_path, 1), _make(tmp_path, 2)
    manual = tmp_path / "myrm-backup-202610010300.zip"
    manual.write_bytes(b"manual")
    notes = tmp_path / "notes.txt"
    notes.write_text("mine")

    removed = prune(tmp_path, keep=2, tag=TAG, just_written=newest.name)

    assert removed == [oldest.name]
    assert not oldest.exists() and middle.exists() and newest.exists()
    assert manual.exists() and notes.exists()


def test_prune_never_touches_another_instances_files_even_when_they_are_older(tmp_path: Path) -> None:
    ours = [_make(tmp_path, day) for day in (10, 11, 12)]
    theirs = [_make(tmp_path, day, tag=OTHER_TAG) for day in (0, 1, 2, 3)]
    their_partial = tmp_path / (backup_name(BASE + timedelta(days=4), OTHER_TAG) + ".partial")
    their_partial.write_bytes(b"in flight on another machine")

    removed = prune(tmp_path, keep=1, tag=TAG, just_written=ours[2].name)

    assert removed == [ours[1].name, ours[0].name]
    assert all(path.exists() for path in theirs) and their_partial.exists()


def test_prune_removes_abandoned_partials_but_not_foreign_partials(tmp_path: Path) -> None:
    only = _make(tmp_path, 0)
    ours = tmp_path / (backup_name(BASE + timedelta(days=5), TAG) + ".partial")
    ours.write_bytes(b"half")
    theirs = tmp_path / "download.zip.partial"
    theirs.write_bytes(b"half")

    prune(tmp_path, keep=3, tag=TAG, just_written=only.name)

    assert not ours.exists()
    assert theirs.exists()


def test_prune_with_fewer_files_than_keep_deletes_nothing(tmp_path: Path) -> None:
    only = _make(tmp_path, 0)

    assert prune(tmp_path, keep=3, tag=TAG, just_written=only.name) == []
    assert only.exists()


def test_a_folder_that_cannot_be_read_is_an_error_not_an_empty_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FileNotFoundError):
        list_backups(tmp_path / "gone", TAG)

    def denied(self: Path) -> NoReturn:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(PermissionError):
        list_backups(tmp_path, TAG)


def test_prune_gives_up_quietly_on_a_folder_it_cannot_read(tmp_path: Path) -> None:
    assert prune(tmp_path / "gone", keep=1, tag=TAG, just_written="x.zip") == []


def test_the_last_backup_is_the_newest_one_not_dated_after_now(tmp_path: Path) -> None:
    _make(tmp_path, 0)
    expected = _make(tmp_path, 2)
    _make(tmp_path, 400)  # written while the clock ran far ahead
    now = BASE + timedelta(days=3)

    last = last_backup(list_backups(tmp_path, TAG), now)

    assert last is not None and last.name == expected.name
    assert last_backup([], now) is None
    assert last_backup(list_backups(tmp_path, TAG)[:1], now) is None  # only the future-dated file is left


def test_a_future_dated_file_cannot_evict_the_backup_just_written(tmp_path: Path) -> None:
    future = _make(tmp_path, 400)
    older = _make(tmp_path, 0)
    just_written = _make(tmp_path, 1)

    removed = prune(tmp_path, keep=1, tag=TAG, just_written=just_written.name)

    assert removed == [older.name]
    assert future.exists() and just_written.exists()


def _make_incomplete(folder: Path, days: int, *, tag: str = TAG) -> Path:
    path = folder / incomplete_name(BASE + timedelta(days=days), tag)
    path.write_bytes(b"x")
    return path


def test_an_incomplete_copy_is_named_apart_and_never_listed_as_a_backup(tmp_path: Path) -> None:
    complete = _make(tmp_path, 0)
    salvage = _make_incomplete(tmp_path, 1)

    assert salvage.name == "myrm-auto-backup-3fa9c2d1-20261002-030000.incomplete.zip"
    assert _names(tmp_path) == [complete.name]


def test_a_complete_backup_supersedes_incomplete_copies_and_sweeps_every_abandoned_partial(tmp_path: Path) -> None:
    old = _make(tmp_path, 0)
    new = _make(tmp_path, 2)
    salvage = _make_incomplete(tmp_path, 1)
    partials = [
        tmp_path / (backup_name(BASE + timedelta(days=3), TAG) + ".partial"),
        tmp_path / (incomplete_name(BASE + timedelta(days=3), TAG) + ".partial"),
    ]
    for partial in partials:
        partial.write_bytes(b"half")

    removed = prune(tmp_path, keep=2, tag=TAG, just_written=new.name)

    assert sorted(removed) == sorted([salvage.name, *(partial.name for partial in partials)])
    assert old.exists() and new.exists()
    assert not salvage.exists() and not any(partial.exists() for partial in partials)


def test_pruning_after_an_incomplete_run_keeps_only_that_copy_and_every_complete_backup(tmp_path: Path) -> None:
    complete = [_make(tmp_path, day) for day in (0, 1, 2)]
    older = _make_incomplete(tmp_path, 3)
    newest = _make_incomplete(tmp_path, 4)
    partial = tmp_path / (incomplete_name(BASE + timedelta(days=5), TAG) + ".partial")
    partial.write_bytes(b"half")

    removed = prune_incomplete(tmp_path, TAG, just_written=newest.name)

    assert sorted(removed) == sorted([older.name, partial.name])
    assert newest.exists() and all(path.exists() for path in complete)


def test_another_instances_incomplete_copies_are_never_touched(tmp_path: Path) -> None:
    mine = _make_incomplete(tmp_path, 1)
    theirs = _make_incomplete(tmp_path, 0, tag=OTHER_TAG)
    their_backup = _make(tmp_path, 0, tag=OTHER_TAG)

    prune_incomplete(tmp_path, TAG, just_written=mine.name)
    prune(tmp_path, keep=1, tag=TAG, just_written="none.zip")

    assert theirs.exists() and their_backup.exists()


def test_pruning_incomplete_copies_gives_up_quietly_on_a_folder_it_cannot_read(tmp_path: Path) -> None:
    assert prune_incomplete(tmp_path / "gone", TAG, just_written="x.incomplete.zip") == []
