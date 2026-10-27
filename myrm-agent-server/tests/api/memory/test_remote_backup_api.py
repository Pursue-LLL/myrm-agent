"""Remote backup HTTP surface: the auto-sync status, unreadable listings and what a manual backup records.

[INPUT]
app.api.memory.operations.backup_remote (router: /backup/remote/*)
app.services.memory.backup.remote_sync.state::RemoteSyncStore

[OUTPUT]
That the status endpoint reports the persisted run state, a listing that cannot be read is an error and not an empty
list, and a manual backup carries this instance's tag and ends a failure streak but never starts one.

[POS]
The real router over a temporary state directory; the backup runner (covered by the round-trip tests) and the remote
storage are replaced, so only the HTTP contract and the recording are asserted.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.operations import backup_remote as api
from app.api.memory.utils import get_crud_memory_manager
from app.services.instance_archive.models import ArchivePaths
from app.services.memory.backup.remote_sync.runner import RemoteBackupResult, RemoteRestoreResult
from app.services.memory.backup.remote_sync.state import RemoteSyncState, RemoteSyncStore
from app.services.memory.backup.remote_sync.storage import RemoteBackupFile, RemoteBackupStrategy, RemoteStorageError
from tests.support.in_memory_remote_backup import InMemoryBackupStrategy
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")
client = TestClient(app)

_PREFIX = "/api/v1/memory/backup/remote"
_WEBDAV = {"provider": "webdav", "webdav": {"host": "https://dav.example.test", "username": "u", "password": "p"}}
_NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


class _UnreadableListing(InMemoryBackupStrategy):
    async def list_files(self) -> list[RemoteBackupFile]:
        raise RemoteStorageError("WebDAV listing failed: HTTP 401")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RemoteSyncStore]:
    sync_store = RemoteSyncStore(ArchivePaths(tmp_path))
    monkeypatch.setattr(api, "default_store", lambda: sync_store)
    app.dependency_overrides[get_crud_memory_manager] = lambda: MagicMock(spec=MemoryManager)
    try:
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            yield sync_store
    finally:
        app.dependency_overrides.pop(get_crud_memory_manager, None)


def _use_strategy(monkeypatch: pytest.MonkeyPatch, strategy: RemoteBackupStrategy) -> None:
    monkeypatch.setattr(api, "_build_strategy", lambda provider, webdav, s3: strategy)


def test_the_status_of_a_sync_that_never_ran_is_empty(store: RemoteSyncStore) -> None:
    response = client.get(f"{_PREFIX}/auto-status")

    assert response.status_code == 200
    assert response.json() == {
        "last_success_at": None,
        "last_attempt_at": None,
        "last_error_code": None,
        "consecutive_failures": 0,
    }


def test_the_status_reports_what_the_scheduled_runs_recorded(store: RemoteSyncStore) -> None:
    store.save(
        RemoteSyncState(
            last_success_at=_NOW - timedelta(days=2),
            last_attempt_at=_NOW,
            last_error_code="upload",
            consecutive_failures=3,
            alerted=True,
        )
    )

    body = client.get(f"{_PREFIX}/auto-status").json()

    assert body == {
        "last_success_at": (_NOW - timedelta(days=2)).isoformat(),
        "last_attempt_at": _NOW.isoformat(),
        "last_error_code": "upload",
        "consecutive_failures": 3,
    }


def test_a_listing_lists_the_backups(store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch) -> None:
    remote = InMemoryBackupStrategy()
    remote._storage["myrm.20260101000000.laptop.1a2b3c4d.linux.json.gz"] = b"x" * 10
    _use_strategy(monkeypatch, remote)

    body = client.post(f"{_PREFIX}/list", json=_WEBDAV).json()

    assert body["total"] == 1
    assert body["files"][0]["file_name"] == "myrm.20260101000000.laptop.1a2b3c4d.linux.json.gz"


def test_a_listing_that_cannot_be_read_is_an_error_and_not_an_empty_list(
    store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_strategy(monkeypatch, _UnreadableListing())

    response = client.post(f"{_PREFIX}/list", json=_WEBDAV)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to list remote backups"


def test_a_manual_backup_carries_this_instances_tag_and_the_device_name_as_typed(
    store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_run(manager: MemoryManager, strategy: RemoteBackupStrategy, **options: object) -> RemoteBackupResult:
        calls.append(options)
        return RemoteBackupResult(status="ok", file_name="myrm.backup.json.gz", size_bytes=12, duration_ms=3.5)

    monkeypatch.setattr(api, "run_remote_backup", fake_run)
    _use_strategy(monkeypatch, InMemoryBackupStrategy())

    body = client.post(f"{_PREFIX}/trigger", json={**_WEBDAV, "device_name": "", "max_backups": 7}).json()

    assert calls == [{"instance_tag": store.tag(), "device_name": "", "max_backups": 7}]
    assert body == {
        "success": True,
        "file_name": "myrm.backup.json.gz",
        "size_bytes": 12,
        "restored_count": None,
        "duration_ms": 3.5,
        "error": None,
        "error_code": None,
    }


def test_a_manual_backup_ends_a_failure_streak(store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.save(
        RemoteSyncState(last_success_at=_NOW - timedelta(days=3), consecutive_failures=4, last_error_code="upload", alerted=True)
    )

    async def fake_run(manager: MemoryManager, strategy: RemoteBackupStrategy, **options: object) -> RemoteBackupResult:
        return RemoteBackupResult(status="ok", file_name="myrm.backup.json.gz")

    monkeypatch.setattr(api, "run_remote_backup", fake_run)
    _use_strategy(monkeypatch, InMemoryBackupStrategy())

    client.post(f"{_PREFIX}/trigger", json=_WEBDAV)

    state = store.load()
    assert (state.consecutive_failures, state.last_error_code, state.alerted) == (0, None, False)
    assert state.last_success_at is not None and state.last_success_at > _NOW


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (RemoteBackupResult(status="failed", error_code="upload", error="Remote upload failed after retries"), "upload"),
        (RemoteBackupResult(status="failed", error_code="snapshot", error="Memory export is incomplete"), "snapshot"),
        (RemoteBackupResult(status="busy", error="Backup already in progress"), "busy"),
    ],
    ids=["upload", "snapshot", "busy"],
)
def test_a_manual_backup_that_does_not_succeed_reports_why_and_never_counts_against_the_schedule(
    store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch, outcome: RemoteBackupResult, code: str
) -> None:
    async def fake_run(manager: MemoryManager, strategy: RemoteBackupStrategy, **options: object) -> RemoteBackupResult:
        return outcome

    monkeypatch.setattr(api, "run_remote_backup", fake_run)
    _use_strategy(monkeypatch, InMemoryBackupStrategy())

    body = client.post(f"{_PREFIX}/trigger", json=_WEBDAV).json()

    assert (body["success"], body["error"], body["error_code"]) == (False, outcome.error, code)
    assert store.load() == RemoteSyncState()


def test_a_restore_reports_the_typed_result(store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_restore(manager: MemoryManager, strategy: RemoteBackupStrategy, file_name: str) -> RemoteRestoreResult:
        return RemoteRestoreResult(success=True, restored_count=3, duration_ms=1.5)

    monkeypatch.setattr(api, "restore_from_remote", fake_restore)
    _use_strategy(monkeypatch, InMemoryBackupStrategy())

    body = client.post(f"{_PREFIX}/restore", json={**_WEBDAV, "file_name": "x.json.gz"}).json()

    assert (body["success"], body["restored_count"], body["duration_ms"], body["error"]) == (True, 3, 1.5, None)


def test_a_delete_that_the_remote_refuses_reports_failure(store: RemoteSyncStore, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_strategy(monkeypatch, InMemoryBackupStrategy())

    body = client.post(f"{_PREFIX}/delete", json={**_WEBDAV, "file_name": "absent.json.gz"}).json()

    assert body == {"success": False}
