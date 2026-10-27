"""Persisted state of the scheduled remote backup and the instance tag it shares with the instance backup.

[INPUT]
app.services.memory.backup.remote_sync.state::RemoteSyncState/RemoteSyncStore
app.services.instance_archive::ArchivePaths, classify_path
app.services.instance_archive.auto_backup.store::AutoBackupStore

[OUTPUT]
What survives a restart, what a damaged file means, and that one instance has exactly one tag.

[POS]
Real files under a temporary state directory; no clock and no network.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.instance_archive.auto_backup.models import INSTANCE_TAG_PATTERN
from app.services.instance_archive.auto_backup.store import AutoBackupStore
from app.services.instance_archive.models import ArchivePaths
from app.services.instance_archive.policy import PathCategory, classify_path
from app.services.memory.backup.remote_sync.state import RemoteSyncState, RemoteSyncStore

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def paths(tmp_path: Path) -> ArchivePaths:
    return ArchivePaths(tmp_path)


def test_a_new_state_has_never_succeeded_and_never_failed() -> None:
    state = RemoteSyncState()
    assert (state.last_success_at, state.last_attempt_at, state.last_error_code) == (None, None, None)
    assert (state.consecutive_failures, state.alerted) == (0, False)


def test_a_missing_file_loads_as_a_fresh_state(paths: ArchivePaths) -> None:
    assert RemoteSyncStore(paths).load() == RemoteSyncState()


def test_what_was_saved_is_what_the_next_start_loads(paths: ArchivePaths) -> None:
    state = RemoteSyncState(
        last_success_at=NOW - timedelta(days=1),
        last_attempt_at=NOW,
        last_error_code="upload",
        consecutive_failures=3,
        alerted=True,
    )

    RemoteSyncStore(paths).save(state)

    assert RemoteSyncStore(paths).load() == state


@pytest.mark.parametrize("content", ["", "not json", "[1, 2]", "null", '"text"'])
def test_a_damaged_file_loads_as_a_fresh_state_instead_of_raising(paths: ArchivePaths, content: str) -> None:
    store = RemoteSyncStore(paths)
    store.save(RemoteSyncState(consecutive_failures=4))
    (paths.root / "remote_memory_backup.json").write_text(content, encoding="utf-8")

    assert store.load() == RemoteSyncState()


def test_hostile_values_are_clamped_or_dropped(paths: ArchivePaths) -> None:
    paths.root.mkdir(parents=True)
    (paths.root / "remote_memory_backup.json").write_text(
        json.dumps(
            {
                "last_success_at": "yesterday",
                "last_attempt_at": "2026-10-26T12:00:00",
                "last_error_code": 42,
                "consecutive_failures": -7,
                "alerted": "yes",
            }
        ),
        encoding="utf-8",
    )

    state = RemoteSyncStore(paths).load()

    assert state.last_success_at is None
    assert state.last_attempt_at == datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # a naive moment is read as UTC
    assert state.last_error_code is None
    assert state.consecutive_failures == 0
    assert state.alerted is False


def test_a_success_clears_the_failure_streak_and_the_alert() -> None:
    failing = RemoteSyncState(
        last_success_at=NOW - timedelta(days=3),
        last_attempt_at=NOW - timedelta(hours=1),
        last_error_code="upload",
        consecutive_failures=5,
        alerted=True,
    )

    assert failing.succeeded(NOW) == RemoteSyncState(last_success_at=NOW, last_attempt_at=NOW)


def test_a_failure_counts_up_and_keeps_the_last_success() -> None:
    state = RemoteSyncState(last_success_at=NOW - timedelta(days=1), consecutive_failures=1, alerted=False)

    failed = state.failed("upload", NOW)

    assert failed.last_success_at == NOW - timedelta(days=1)
    assert (failed.last_attempt_at, failed.last_error_code, failed.consecutive_failures) == (NOW, "upload", 2)


def test_marking_the_alert_does_not_touch_anything_else() -> None:
    state = RemoteSyncState(consecutive_failures=2, last_error_code="upload")
    assert state.mark_alerted() == RemoteSyncState(consecutive_failures=2, last_error_code="upload", alerted=True)


def test_the_state_lives_in_the_runtime_directory_so_an_instance_import_never_replaces_it(paths: ArchivePaths) -> None:
    store = RemoteSyncStore(paths)
    store.save(RemoteSyncState(consecutive_failures=1))

    relative = (paths.root / "remote_memory_backup.json").relative_to(paths.state_dir)

    assert classify_path(relative.parts).category is PathCategory.RUNTIME


def test_the_tag_is_created_once_and_stays_the_same(paths: ArchivePaths) -> None:
    first = RemoteSyncStore(paths).tag()

    assert re.fullmatch(INSTANCE_TAG_PATTERN, first)
    assert RemoteSyncStore(paths).tag() == first


def test_one_instance_has_one_tag_for_the_instance_backup_and_the_remote_backup(paths: ArchivePaths) -> None:
    assert RemoteSyncStore(paths).tag() == AutoBackupStore(paths).tag()
    assert AutoBackupStore(paths).tag() == RemoteSyncStore(paths).tag()


def test_two_stores_first_used_at_the_same_moment_still_agree_on_one_tag(
    paths: ArchivePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_token = secrets.token_hex
    calls = threading.Lock()
    minted: list[str] = []

    def slow_token(nbytes: int) -> str:
        time.sleep(0.05)  # the window in which a second store would otherwise mint its own tag
        token = real_token(nbytes)
        with calls:
            minted.append(token)
        return token

    monkeypatch.setattr(secrets, "token_hex", slow_token)
    stores = [RemoteSyncStore(paths), AutoBackupStore(paths), RemoteSyncStore(paths), AutoBackupStore(paths)]
    results: list[str] = []
    barrier = threading.Barrier(len(stores))

    def first_use(store: RemoteSyncStore | AutoBackupStore) -> None:
        barrier.wait()
        results.append(store.tag())

    threads = [threading.Thread(target=first_use, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(results)) == 1
    assert len(minted) == 1
