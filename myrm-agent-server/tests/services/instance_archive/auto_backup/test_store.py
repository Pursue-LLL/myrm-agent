"""Settings, run state and instance tag persistence: bounds, hostile files, and never travelling with a backup."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.instance_archive.auto_backup.models import (
    DEFAULT_KEEP,
    INSTANCE_TAG_PATTERN,
    KEEP_MAX,
    KEEP_MIN,
    AutoBackupSettings,
    AutoBackupState,
    Frequency,
)
from app.services.instance_archive.auto_backup.store import AutoBackupStore
from app.services.instance_archive.models import ArchivePaths
from app.services.instance_archive.policy import classify_path


def _store(tmp_path: Path) -> tuple[AutoBackupStore, Path]:
    paths = ArchivePaths(tmp_path)
    return AutoBackupStore(paths), paths.root / "auto_backup.json"


def test_missing_file_means_off_with_defaults(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)

    settings, state = store.load()

    assert settings == AutoBackupSettings(enabled=False, frequency=Frequency.DAILY, keep=DEFAULT_KEEP, directory=None)
    assert state == AutoBackupState()


def test_settings_and_state_roundtrip_and_do_not_overwrite_each_other(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    moment = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)

    store.save_settings(AutoBackupSettings(enabled=True, frequency=Frequency.WEEKLY, keep=5, directory="/mnt/backup"))
    store.save_state(AutoBackupState(last_attempt_at=moment, consecutive_failures=2, last_error_code="export_failed"))
    store.save_settings(AutoBackupSettings(enabled=True, frequency=Frequency.WEEKLY, keep=7, directory=None))

    settings, state = store.load()
    assert (settings.keep, settings.directory, settings.frequency) == (7, None, Frequency.WEEKLY)
    assert (state.last_attempt_at, state.consecutive_failures, state.last_error_code) == (moment, 2, "export_failed")


def test_hostile_values_are_clamped_or_defaulted(tmp_path: Path) -> None:
    store, file = _store(tmp_path)
    file.parent.mkdir(parents=True)
    file.write_text(
        json.dumps(
            {
                "settings": {"enabled": "yes", "frequency": "hourly", "keep": 10_000, "directory": "  "},
                "state": {
                    "last_attempt_at": "not a date",
                    "consecutive_failures": -3,
                    "last_error_code": 7,
                },
            }
        )
    )

    settings, state = store.load()

    assert settings == AutoBackupSettings(enabled=False, frequency=Frequency.DAILY, keep=KEEP_MAX, directory=None)
    assert state == AutoBackupState()
    file.write_text(json.dumps({"settings": {"keep": 0}}))
    assert store.load()[0].keep == KEEP_MIN


def test_corrupt_or_non_object_file_falls_back_to_defaults(tmp_path: Path) -> None:
    store, file = _store(tmp_path)
    file.parent.mkdir(parents=True)
    for content in ("{broken", "[1, 2]", ""):
        file.write_text(content)
        assert store.load() == (AutoBackupSettings(), AutoBackupState())


def test_naive_timestamps_are_read_as_utc(tmp_path: Path) -> None:
    store, file = _store(tmp_path)
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps({"state": {"last_attempt_at": "2026-10-13T03:00:00"}}))

    assert store.load()[1].last_attempt_at == datetime(2026, 10, 13, 3, 0, tzinfo=UTC)


def test_the_tag_is_made_once_and_survives_every_later_save(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    tag_file = tmp_path / "instance_archive" / "auto_backup_instance.json"

    tag = store.tag()
    store.save_settings(AutoBackupSettings(enabled=True))
    store.save_state(AutoBackupState(consecutive_failures=1))

    assert re.fullmatch(INSTANCE_TAG_PATTERN, tag)
    assert store.tag() == tag == json.loads(tag_file.read_text())["tag"]
    assert AutoBackupStore(ArchivePaths(tmp_path)).tag() == tag  # a restart keeps it
    assert store.load()[0].enabled and store.load()[1].consecutive_failures == 1  # settings and tag never touch each other


def test_two_instances_get_different_tags(tmp_path: Path) -> None:
    first, _ = _store(tmp_path / "a")
    second, _ = _store(tmp_path / "b")

    assert first.tag() != second.tag()


def test_a_damaged_tag_file_is_replaced_by_a_valid_tag(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    tag_file = tmp_path / "instance_archive" / "auto_backup_instance.json"
    tag_file.parent.mkdir(parents=True)
    for damaged in ('{"tag": "../../etc"}', '{"tag": "ABCDEF12"}', '{"tag": "abc"}', '{"tag": 7}', "[1]", "{broken", ""):
        tag_file.write_text(damaged)

        assert re.fullmatch(INSTANCE_TAG_PATTERN, store.tag())


def test_reading_the_tag_never_rewrites_the_settings_even_when_they_cannot_be_read(tmp_path: Path) -> None:
    store, file = _store(tmp_path)
    file.parent.mkdir(parents=True)
    file.write_text("{broken")

    store.tag()

    assert file.read_text() == "{broken"


def test_a_tag_file_that_cannot_be_read_is_an_error_not_a_reason_to_mint_a_new_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _ = _store(tmp_path)
    tag = store.tag()
    real_read_text = Path.read_text

    def locked(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "auto_backup_instance.json":
            raise PermissionError("locked by another process")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", locked)
    with pytest.raises(PermissionError):
        store.tag()
    monkeypatch.undo()

    assert store.tag() == tag  # the unreadable moment did not replace it


@pytest.mark.parametrize("name", ["auto_backup.json", "auto_backup_instance.json"])
def test_the_files_are_runtime_state_that_never_travel_in_a_backup(tmp_path: Path, name: str) -> None:
    file = ArchivePaths(tmp_path).root / name

    decision = classify_path(file.relative_to(tmp_path).parts)

    assert not decision.include
