"""S3 remote backup client: operations, key prefix and client lifecycle.

[INPUT]
app.services.memory.backup.remote_sync.storage.s3::S3BackupStrategy/S3BackupConfig

[OUTPUT]
What each S3 operation sends, how a listing is read (every page, never a part), and that every operation closes the client
it opened.

[POS]
The real strategy with a fake ``aioboto3`` module standing in for the network; the fake pages its listings the way S3 does.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import BinaryIO

import pytest

from app.services.memory.backup.remote_sync.storage import RemoteStorageError, S3BackupConfig, S3BackupStrategy
from app.services.memory.backup.remote_sync.storage import s3 as s3_module

_DEFAULT_MODIFIED = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeS3:
    """A bucket held in memory, plus a record of how clients were opened and closed."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.modified: dict[str, datetime] = {}
        self.opened: list[dict[str, object]] = []
        self.closed = 0
        self.failing = False
        self.page_size = 1000  # S3 returns at most 1000 keys per request
        self.list_requests: list[dict[str, object]] = []
        self.fail_on_list_request: int | None = None  # 1-based: that request and every later one raises
        self.drop_continuation_token = False  # a misbehaving server: truncated, yet no token to continue with


class _FakeClient:
    def __init__(self, s3: _FakeS3) -> None:
        self._s3 = s3

    def _reach(self) -> None:
        if self._s3.failing:
            raise ConnectionError("endpoint unreachable")

    async def head_bucket(self, *, Bucket: str) -> None:
        self._reach()

    async def upload_fileobj(self, fileobj: BinaryIO, bucket: str, key: str) -> None:
        self._reach()
        self._s3.objects[key] = fileobj.read()

    async def download_fileobj(self, bucket: str, key: str, fileobj: BinaryIO) -> None:
        self._reach()
        fileobj.write(self._s3.objects[key])

    async def list_objects_v2(self, *, Bucket: str, Prefix: str, **extra: str) -> dict[str, object]:
        self._reach()
        self._s3.list_requests.append({"Prefix": Prefix, **extra})
        if self._s3.fail_on_list_request is not None and len(self._s3.list_requests) >= self._s3.fail_on_list_request:
            raise ConnectionError("endpoint unreachable")
        keys = sorted(key for key in self._s3.objects if key.startswith(Prefix))  # S3 lists in ascending key order
        start = int(extra["ContinuationToken"]) if "ContinuationToken" in extra else 0
        page = keys[start : start + self._s3.page_size]
        response: dict[str, object] = {"IsTruncated": start + len(page) < len(keys)}
        if page:
            response["Contents"] = [
                {"Key": key, "LastModified": self._s3.modified.get(key, _DEFAULT_MODIFIED), "Size": len(self._s3.objects[key])}
                for key in page
            ]
        if response["IsTruncated"] and not self._s3.drop_continuation_token:
            response["NextContinuationToken"] = str(start + len(page))
        return response

    async def delete_object(self, *, Bucket: str, Key: str) -> None:
        self._reach()
        self._s3.objects.pop(Key, None)


class _ClientContext:
    def __init__(self, s3: _FakeS3, options: dict[str, object]) -> None:
        self._s3 = s3
        self._options = options

    async def __aenter__(self) -> _FakeClient:
        self._s3.opened.append(self._options)
        return _FakeClient(self._s3)

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self._s3.closed += 1


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> _FakeS3:
    state = _FakeS3()

    class _Session:
        def client(self, service_name: str, **options: object) -> _ClientContext:
            return _ClientContext(state, {"service": service_name, **options})

    monkeypatch.setitem(sys.modules, "aioboto3", SimpleNamespace(Session=_Session))
    return state


def _strategy(**overrides: object) -> S3BackupStrategy:
    settings: dict[str, object] = {
        "endpoint": "https://s3.example.test",
        "region": "eu-west-1",
        "bucket": "vault",
        "access_key_id": "key-id",
        "secret_access_key": "secret",
        "prefix": "myrm-backups/",
        "force_path_style": True,
    }
    return S3BackupStrategy(S3BackupConfig(**{**settings, **overrides}))


async def test_a_backup_round_trips_under_the_configured_prefix(tmp_path: Path, s3: _FakeS3) -> None:
    strategy = _strategy()
    source = tmp_path / "backup.json.gz"
    source.write_bytes(b"memories")

    assert await strategy.upload(source, "myrm.1.json.gz") is True
    assert s3.objects == {"myrm-backups/myrm.1.json.gz": b"memories"}

    restored = tmp_path / "restored" / "backup.json.gz"
    assert await strategy.download("myrm.1.json.gz", restored) is True
    assert restored.read_bytes() == b"memories"

    assert await strategy.delete("myrm.1.json.gz") is True
    assert s3.objects == {}


async def test_a_listing_names_files_without_the_prefix_and_skips_folder_placeholders(s3: _FakeS3) -> None:
    s3.objects = {
        "myrm-backups/": b"",
        "myrm-backups/old.json.gz": b"1",
        "myrm-backups/sub/": b"",
        "myrm-backups/new.json.gz": b"22",
        "elsewhere/other.json.gz": b"333",
    }
    s3.modified = {
        "myrm-backups/old.json.gz": datetime(2026, 1, 1),  # a server may report naive times
        "myrm-backups/new.json.gz": datetime(2026, 1, 2, tzinfo=UTC),
    }

    files = await _strategy().list_files()

    assert [(f.file_name, f.size_bytes, f.modified_time) for f in files] == [
        ("new.json.gz", 2, datetime(2026, 1, 2, tzinfo=UTC)),
        ("old.json.gz", 1, datetime(2026, 1, 1, tzinfo=UTC)),
    ]


async def test_an_empty_bucket_lists_nothing(s3: _FakeS3) -> None:
    assert await _strategy().list_files() == []


async def test_a_listing_follows_every_page_so_a_backup_behind_a_thousand_other_keys_is_found(s3: _FakeS3) -> None:
    # S3 lists in key order: a folder with many files that sort before "myrm." would hide every backup on page one.
    s3.objects = {f"myrm-backups/a-{n:04d}.txt": b"x" for n in range(2500)}
    s3.objects["myrm-backups/myrm.20261026120000.laptop.1a2b3c4d.linux.json.gz"] = b"backup"

    files = await _strategy().list_files()

    assert len(files) == 2501
    assert "myrm.20261026120000.laptop.1a2b3c4d.linux.json.gz" in {f.file_name for f in files}
    assert [request.get("ContinuationToken") for request in s3.list_requests] == [None, "1000", "2000"]
    assert s3.closed == 1  # one client serves every page


async def test_a_listing_that_fills_exactly_one_page_is_not_followed_by_another_request(s3: _FakeS3) -> None:
    s3.objects = {f"myrm-backups/b-{n:04d}.json.gz": b"x" for n in range(1000)}

    assert len(await _strategy().list_files()) == 1000
    assert len(s3.list_requests) == 1


async def test_a_listing_longer_than_the_page_limit_raises_instead_of_returning_a_part(
    s3: _FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(s3_module, "_LIST_PAGE_LIMIT", 3)
    s3.page_size = 1
    s3.objects = {f"myrm-backups/c-{n}.json.gz": b"x" for n in range(5)}

    with pytest.raises(RemoteStorageError, match="refusing to read a partial listing"):
        await _strategy().list_files()
    assert len(s3.list_requests) == 3
    assert s3.closed == 1


async def test_a_listing_that_ends_exactly_at_the_page_limit_is_complete_and_does_not_raise(
    s3: _FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(s3_module, "_LIST_PAGE_LIMIT", 3)
    s3.page_size = 1
    s3.objects = {f"myrm-backups/d-{n}.json.gz": b"x" for n in range(3)}

    assert len(await _strategy().list_files()) == 3


async def test_a_truncated_page_without_a_continuation_token_raises(s3: _FakeS3) -> None:
    s3.page_size = 1
    s3.drop_continuation_token = True
    s3.objects = {"myrm-backups/e-1.json.gz": b"x", "myrm-backups/e-2.json.gz": b"x"}

    with pytest.raises(RemoteStorageError, match="continuation token"):
        await _strategy().list_files()


async def test_a_later_page_that_cannot_be_read_fails_the_whole_listing_and_closes_the_client(s3: _FakeS3) -> None:
    s3.page_size = 1
    s3.fail_on_list_request = 2
    s3.objects = {"myrm-backups/f-1.json.gz": b"x", "myrm-backups/f-2.json.gz": b"x"}

    with pytest.raises(ConnectionError):
        await _strategy().list_files()  # the first page alone must not pass for the whole listing
    assert s3.closed == 1


async def test_every_operation_opens_one_client_with_the_configured_endpoint_and_closes_it(tmp_path: Path, s3: _FakeS3) -> None:
    strategy = _strategy()
    source = tmp_path / "backup.json.gz"
    source.write_bytes(b"memories")

    await strategy.check_connection()
    await strategy.upload(source, "n")
    await strategy.download("n", tmp_path / "out")
    await strategy.list_files()
    await strategy.delete("n")

    assert len(s3.opened) == 5
    assert s3.closed == 5
    opened = s3.opened[0]
    assert (opened["service"], opened["region_name"], opened["endpoint_url"]) == (
        "s3",
        "eu-west-1",
        "https://s3.example.test",
    )
    assert (opened["aws_access_key_id"], opened["aws_secret_access_key"]) == ("key-id", "secret")
    config = opened["config"]
    assert (config.s3, config.connect_timeout, config.read_timeout) == ({"addressing_style": "path"}, 15, 300)


async def test_blank_region_and_endpoint_fall_back_to_the_provider_defaults(s3: _FakeS3) -> None:
    await _strategy(region="", endpoint="", force_path_style=False).check_connection()

    opened = s3.opened[0]
    assert opened["region_name"] == "us-east-1"
    assert "endpoint_url" not in opened
    assert opened["config"].s3 is None


async def test_failures_are_reported_as_unsuccessful_a_listing_raises_and_the_client_is_still_closed(
    tmp_path: Path, s3: _FakeS3
) -> None:
    strategy = _strategy()
    source = tmp_path / "backup.json.gz"
    source.write_bytes(b"memories")
    s3.failing = True

    assert await strategy.check_connection() is False
    assert await strategy.upload(source, "n") is False
    assert await strategy.download("n", tmp_path / "out") is False
    with pytest.raises(ConnectionError):
        await strategy.list_files()  # an unreadable bucket is not an empty one
    assert await strategy.delete("n") is False
    s3.failing = False
    assert await strategy.upload(tmp_path / "absent.json.gz", "n") is False

    assert s3.closed == 6
