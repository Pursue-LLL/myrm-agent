"""Remote backup file names and rotation.

[INPUT]
app.services.memory.backup.remote_sync.runner::run_remote_backup

[OUTPUT]
What a backup cycle uploads, and what it deletes from a folder or bucket other files and other instances share.

[POS]
Real memory stores and the real runner; only the remote storage is an in-memory double, and it lists
in whatever order and with whatever modified times a test needs.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.memory.backup.remote_sync import runner
from app.services.memory.backup.remote_sync.runner import run_remote_backup
from app.services.memory.backup.remote_sync.storage import RemoteBackupFile
from tests.support.in_memory_remote_backup import InMemoryBackupStrategy
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration

TAG = "1a2b3c4d"
OTHER_TAG = "deadbeef"


class _ShuffledListing(InMemoryBackupStrategy):
    """Lists oldest first with one modified time for every file: an order and times a server may hand back."""

    async def list_files(self) -> list[RemoteBackupFile]:
        modified = datetime(2026, 1, 1, tzinfo=UTC)
        return [
            RemoteBackupFile(file_name=name, modified_time=modified, size_bytes=len(data))
            for name, data in sorted(self._storage.items())
        ]


class _StubbornDelete(_ShuffledListing):
    """Refuses to delete one file, as a locked or read-only remote file would."""

    def __init__(self, stubborn: str) -> None:
        super().__init__()
        self._stubborn = stubborn

    async def delete(self, remote_name: str) -> bool:
        return False if remote_name == self._stubborn else await super().delete(remote_name)


class _UnreadableListing(InMemoryBackupStrategy):
    """Accepts uploads but cannot list, as a server that forbids PROPFIND or ListObjects does."""

    async def list_files(self) -> list[RemoteBackupFile]:
        raise ConnectionError("listing refused")


@pytest.fixture(autouse=True)
def _linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "platform", SimpleNamespace(system=lambda: "Linux"))


def _backup_name(device: str, day: int, tag: str = TAG, platform_label: str = "linux") -> str:
    return f"myrm.202601{day:02d}000000.{device}.{tag}.{platform_label}.json.gz"


def _seed(remote: InMemoryBackupStrategy, *names: str) -> None:
    for name in names:
        remote._storage[name] = b"old"


async def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remote: InMemoryBackupStrategy,
    device: str,
    max_backups: int,
    tag: str = TAG,
) -> str:
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        result = await run_remote_backup(manager, remote, instance_tag=tag, device_name=device, max_backups=max_backups)
    assert result.status == "ok"
    assert result.file_name is not None
    return result.file_name


async def test_rotation_keeps_the_newest_backups_whatever_order_the_server_lists_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _ShuffledListing()
    _seed(remote, *(_backup_name("laptop", day) for day in range(1, 7)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=3)

    assert sorted(remote._storage) == sorted([_backup_name("laptop", 5), _backup_name("laptop", 6), uploaded])


@pytest.mark.parametrize(("max_backups", "kept_older"), [(1, 0), (3, 2)])
async def test_the_backup_just_uploaded_is_kept_even_when_older_files_carry_later_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_backups: int, kept_older: int
) -> None:
    # Stamped by a clock that ran ahead: by name these outrank any backup made now.
    ahead = [f"myrm.209901{day:02d}000000.laptop.{TAG}.linux.json.gz" for day in range(1, 4)]
    remote = _ShuffledListing()
    _seed(remote, *ahead)

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=max_backups)

    assert sorted(remote._storage) == sorted([*ahead[len(ahead) - kept_older :], uploaded])


async def test_rotation_never_deletes_a_file_it_did_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    foreign = [
        "laptop-linux-notes.gz",
        "photos.laptop.linux.tar.gz",
        f"myrm.notes.laptop.{TAG}.linux.json.gz",
        f"myrm.20260101000000.laptop.{TAG}.linux.json.gz.bak",
        "myrm.20260101000000.laptop.linux.json.gz",  # written under the host-name scheme, which carries no instance
        "myrm.20260101000000.laptop.1A2B3C4D.linux.json.gz",  # not a tag this module writes
        "myrm.20260101000000.laptop.1a2b3c.linux.json.gz",
    ]
    remote = _ShuffledListing()
    _seed(remote, *foreign, *(_backup_name("laptop", day) for day in range(1, 4)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=1)

    assert sorted(remote._storage) == sorted([*foreign, uploaded])


async def test_two_instances_that_share_a_folder_and_a_device_name_never_rotate_each_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _ShuffledListing()
    theirs = [_backup_name("laptop", day, OTHER_TAG) for day in range(1, 5)]
    _seed(remote, *theirs, *(_backup_name("laptop", day) for day in range(1, 5)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=2)

    assert sorted(remote._storage) == sorted([*theirs, _backup_name("laptop", 4), uploaded])


async def test_an_instance_that_changes_its_device_name_keeps_rotating_its_own_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _ShuffledListing()
    _seed(remote, *(_backup_name("old-laptop", day) for day in range(1, 5)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "new-laptop", max_backups=2)

    assert sorted(remote._storage) == sorted([_backup_name("old-laptop", 4), uploaded])


async def test_backups_of_one_instance_rotate_together_whatever_platform_they_were_made_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _ShuffledListing()
    _seed(remote, *(_backup_name("laptop", day, platform_label="darwin") for day in range(1, 5)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=2)

    assert sorted(remote._storage) == sorted([_backup_name("laptop", 4, platform_label="darwin"), uploaded])


@pytest.mark.parametrize("device", ["Yulus-MacBook-Pro.local", "cafebabe", "a.1a2b3c4d.b"])
async def test_rotation_reaches_the_backups_of_a_device_whose_name_has_dots_or_looks_like_a_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, device: str
) -> None:
    remote = _ShuffledListing()
    _seed(remote, *(_backup_name(device, day) for day in range(1, 5)))

    uploaded = await _run(tmp_path, monkeypatch, remote, device, max_backups=2)

    assert sorted(remote._storage) == sorted([_backup_name(device, 4), uploaded])


async def test_rotation_continues_past_a_file_that_cannot_be_deleted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _StubbornDelete(_backup_name("laptop", 1))
    _seed(remote, *(_backup_name("laptop", day) for day in range(1, 5)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=2)

    assert sorted(remote._storage) == sorted([_backup_name("laptop", 1), _backup_name("laptop", 4), uploaded])


async def test_rotation_is_off_when_max_backups_is_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _ShuffledListing()
    old = [_backup_name("laptop", day) for day in range(1, 5)]
    _seed(remote, *old)

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=0)

    assert sorted(remote._storage) == sorted([*old, uploaded])


async def test_a_listing_that_cannot_be_read_costs_nothing_and_never_turns_a_stored_backup_into_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _UnreadableListing()
    _seed(remote, *(_backup_name("laptop", day) for day in range(1, 4)))

    uploaded = await _run(tmp_path, monkeypatch, remote, "laptop", max_backups=1)

    assert uploaded in remote._storage
    assert len(remote._storage) == 4


@pytest.mark.parametrize(
    ("device", "label"),
    [
        ("laptop", "laptop"),
        ("Yulus-MacBook-Pro.local", "Yulus-MacBook-Pro.local"),
        ("小明的电脑", "小明的电脑"),
        ("my/laptop #1?100%", "my-laptop-1-100"),
        ("../etc", "etc"),
        ("///", "unknown"),
        ("x" * 200, "x" * 64),
    ],
)
async def test_the_device_name_is_made_safe_for_a_remote_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, device: str, label: str
) -> None:
    remote = InMemoryBackupStrategy()

    uploaded = await _run(tmp_path, monkeypatch, remote, device, max_backups=5)

    assert re.fullmatch(rf"myrm\.[0-9]{{14}}\.{re.escape(label)}\.{TAG}\.linux\.json\.gz", uploaded)
    assert list(remote._storage) == [uploaded]
