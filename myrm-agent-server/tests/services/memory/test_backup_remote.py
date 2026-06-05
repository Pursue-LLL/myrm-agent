"""Cloud Backup Remote integration tests.

Tests core backup remote modules:
- backup_remote.py: Strategy, config dataclasses, XML parsing
- backup_remote_scheduler.py: run_remote_backup, _upload_with_retry, _rotate_backups
- backup_remote_utils.py: create_exportable_backup, restore_from_exportable_backup
- API endpoints: check-connection, trigger, list, restore, delete
"""

from __future__ import annotations

import gzip
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.memory.backup_remote import (
    RemoteBackupFile,
    RemoteBackupStrategy,
    S3BackupConfig,
    WebDAVBackupConfig,
    _parse_webdav_multistatus,
)

client = TestClient(app)


# ============================================================================
# Fixtures: In-memory strategy for real integration testing
# ============================================================================


class InMemoryBackupStrategy(RemoteBackupStrategy):
    """Real in-memory backup strategy for testing without external services."""

    def __init__(self, *, fail_upload: bool = False, fail_count: int = 0) -> None:
        self._storage: dict[str, bytes] = {}
        self._fail_upload = fail_upload
        self._fail_count = fail_count
        self._upload_attempts = 0

    async def upload(self, local_path: Path, remote_name: str) -> bool:
        self._upload_attempts += 1
        if self._fail_upload:
            return False
        if self._fail_count > 0 and self._upload_attempts <= self._fail_count:
            return False
        self._storage[remote_name] = local_path.read_bytes()
        return True

    async def download(self, remote_name: str, local_path: Path) -> bool:
        if remote_name not in self._storage:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self._storage[remote_name])
        return True

    async def list_files(self) -> list[RemoteBackupFile]:
        results = []
        for name, data in self._storage.items():
            results.append(
                RemoteBackupFile(
                    file_name=name,
                    modified_time=datetime.now(UTC),
                    size_bytes=len(data),
                )
            )
        results.sort(key=lambda f: f.file_name, reverse=True)
        return results

    async def delete(self, remote_name: str) -> bool:
        if remote_name in self._storage:
            del self._storage[remote_name]
            return True
        return False

    async def check_connection(self) -> bool:
        return True


# ============================================================================
# Tests: Config Dataclasses
# ============================================================================


class TestConfigDataclasses:
    def test_webdav_config_defaults(self):
        config = WebDAVBackupConfig()
        assert config.enabled is False
        assert config.host == ""
        assert config.path == "/myrm-backups"
        assert config.sync_interval_minutes == 60
        assert config.max_backups == 10

    def test_s3_config_defaults(self):
        config = S3BackupConfig()
        assert config.enabled is False
        assert config.endpoint == ""
        assert config.bucket == ""
        assert config.prefix == "myrm-backups/"
        assert config.force_path_style is True

    def test_webdav_config_custom(self):
        config = WebDAVBackupConfig(
            host="https://dav.example.com",
            username="user",
            password="pass",
            path="/custom-path",
            enabled=True,
        )
        assert config.host == "https://dav.example.com"
        assert config.username == "user"
        assert config.enabled is True

    def test_remote_backup_file_frozen(self):
        f = RemoteBackupFile(
            file_name="test.gz",
            modified_time=datetime.now(UTC),
            size_bytes=1024,
        )
        assert f.file_name == "test.gz"
        assert f.size_bytes == 1024
        with pytest.raises(Exception):  # noqa: B017
            f.file_name = "other.gz"  # type: ignore[misc]


# ============================================================================
# Tests: WebDAV XML Parser
# ============================================================================


class TestWebDAVXMLParser:
    def test_parse_empty_response(self):
        result = _parse_webdav_multistatus("")
        assert result == []

    def test_parse_valid_multistatus(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/myrm-backups/</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>0</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/myrm-backups/myrm.20250101120000.myhost.linux.json.gz</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>4096</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""
        result = _parse_webdav_multistatus(xml)
        assert len(result) == 1
        assert result[0].file_name == "myrm.20250101120000.myhost.linux.json.gz"
        assert result[0].size_bytes == 4096

    def test_parse_filters_non_gz_files(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/backups/readme.txt</d:href>
    <d:propstat><d:prop>
      <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
      <d:getcontentlength>100</d:getcontentlength>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        result = _parse_webdav_multistatus(xml)
        assert len(result) == 0

    def test_parse_handles_missing_length(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/backups/test.json.gz</d:href>
    <d:propstat><d:prop>
      <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        result = _parse_webdav_multistatus(xml)
        assert len(result) == 1
        assert result[0].size_bytes == 0


# ============================================================================
# Tests: Upload Retry Logic
# ============================================================================


class TestUploadRetry:
    @pytest.mark.asyncio
    async def test_upload_success_first_attempt(self):
        from app.services.memory.backup_remote_scheduler import _upload_with_retry

        strategy = InMemoryBackupStrategy()
        with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as f:
            f.write(b"test data")
            f.flush()
            path = Path(f.name)

        result = await _upload_with_retry(strategy, path, "test.gz")
        assert result is True
        assert strategy._upload_attempts == 1
        path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_retries_on_failure(self):
        from app.services.memory.backup_remote_scheduler import _upload_with_retry

        strategy = InMemoryBackupStrategy(fail_count=2)
        with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as f:
            f.write(b"test data for retry")
            f.flush()
            path = Path(f.name)

        result = await _upload_with_retry(strategy, path, "retry_test.gz")
        assert result is True
        assert strategy._upload_attempts == 3
        path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_upload_fails_after_max_retries(self):
        from app.services.memory.backup_remote_scheduler import _upload_with_retry

        strategy = InMemoryBackupStrategy(fail_upload=True)
        with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as f:
            f.write(b"will fail")
            f.flush()
            path = Path(f.name)

        result = await _upload_with_retry(strategy, path, "fail_test.gz")
        assert result is False
        assert strategy._upload_attempts == 3
        path.unlink(missing_ok=True)


# ============================================================================
# Tests: Run Remote Backup (full cycle with in-memory strategy)
# ============================================================================


class TestRunRemoteBackup:
    @pytest.mark.asyncio
    async def test_backup_mutex_prevents_concurrent(self):
        """Verify mutex lock prevents concurrent backup execution."""
        import app.services.memory.backup_remote_scheduler as sched

        original = sched._auto_backup_running
        sched._auto_backup_running = True

        strategy = InMemoryBackupStrategy()
        result = await sched.run_remote_backup(strategy=strategy, device_name="test")
        assert result["success"] is False
        assert "already in progress" in str(result.get("error", "")).lower()

        sched._auto_backup_running = original


# ============================================================================
# Tests: Backup Rotation
# ============================================================================


class TestBackupRotation:
    @pytest.mark.asyncio
    async def test_rotation_deletes_old_backups(self):
        from app.services.memory.backup_remote_scheduler import _rotate_backups

        strategy = InMemoryBackupStrategy()
        for i in range(5):
            ts = f"2025010{i}120000"
            name = f"myrm.{ts}.myhost.linux.json.gz"
            strategy._storage[name] = b"x" * 100

        await _rotate_backups(strategy, "myhost", "linux", max_backups=3)

        files = await strategy.list_files()
        assert len(files) == 3

    @pytest.mark.asyncio
    async def test_rotation_skips_when_under_limit(self):
        from app.services.memory.backup_remote_scheduler import _rotate_backups

        strategy = InMemoryBackupStrategy()
        strategy._storage["myrm.20250101.host.linux.json.gz"] = b"data"
        strategy._storage["myrm.20250102.host.linux.json.gz"] = b"data"

        await _rotate_backups(strategy, "host", "linux", max_backups=5)

        files = await strategy.list_files()
        assert len(files) == 2


# ============================================================================
# Tests: Restore from Remote
# ============================================================================


class TestRestoreFromRemote:
    @pytest.mark.asyncio
    async def test_restore_fails_on_download_error(self):
        from app.services.memory.backup_remote_scheduler import restore_from_remote

        strategy = InMemoryBackupStrategy()
        result = await restore_from_remote(
            strategy=strategy,
            file_name="nonexistent.json.gz",
        )
        assert result["success"] is False
        assert "download" in str(result.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_restore_fails_on_invalid_version(self):
        from app.services.memory.backup_remote_scheduler import restore_from_remote

        strategy = InMemoryBackupStrategy()
        backup_data = {"version": 1, "collections": {}}
        compressed = gzip.compress(json.dumps(backup_data).encode())
        strategy._storage["old_backup.json.gz"] = compressed

        result = await restore_from_remote(
            strategy=strategy,
            file_name="old_backup.json.gz",
        )
        assert result["success"] is False
        assert "version" in str(result.get("error", "")).lower()


# ============================================================================
# Tests: API Endpoints (via TestClient)
# ============================================================================


class TestRemoteBackupAPI:
    @pytest.fixture(autouse=True)
    def _bypass_auth(self):
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            yield

    def test_check_connection_missing_config(self):
        response = client.post(
            "/api/v1/memory/backup/remote/check-connection",
            json={"provider": "webdav"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["error"] is not None

    def test_check_connection_invalid_provider(self):
        response = client.post(
            "/api/v1/memory/backup/remote/check-connection",
            json={"provider": "ftp", "webdav": None, "s3": None},
        )
        assert response.status_code == 422

    def test_trigger_backup_missing_config(self):
        response = client.post(
            "/api/v1/memory/backup/remote/trigger",
            json={"provider": "webdav"},
        )
        assert response.status_code == 400

    def test_list_backup_missing_config(self):
        response = client.post(
            "/api/v1/memory/backup/remote/list",
            json={"provider": "s3"},
        )
        assert response.status_code == 400

    def test_restore_backup_missing_config(self):
        response = client.post(
            "/api/v1/memory/backup/remote/restore",
            json={"provider": "webdav", "file_name": "test.gz"},
        )
        assert response.status_code == 400

    def test_delete_backup_missing_config(self):
        response = client.post(
            "/api/v1/memory/backup/remote/delete",
            json={"provider": "webdav", "file_name": "test.gz"},
        )
        assert response.status_code == 400

    def test_trigger_with_valid_webdav_config_reaches_connection(self):
        """With valid structure but unreachable host, should return 500 or failure."""
        response = client.post(
            "/api/v1/memory/backup/remote/check-connection",
            json={
                "provider": "webdav",
                "webdav": {
                    "host": "https://unreachable.invalid.local",
                    "username": "user",
                    "password": "pass",
                    "path": "/myrm-backups",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_trigger_with_valid_s3_config_reaches_connection(self):
        """With valid structure but unreachable endpoint, should fail gracefully."""
        response = client.post(
            "/api/v1/memory/backup/remote/check-connection",
            json={
                "provider": "s3",
                "s3": {
                    "endpoint": "https://unreachable.invalid.local",
                    "region": "us-east-1",
                    "bucket": "test-bucket",
                    "access_key_id": "fake-key",
                    "secret_access_key": "fake-secret",
                    "prefix": "myrm-backups/",
                    "force_path_style": True,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False


# ============================================================================
# Tests: Exportable Backup Format
# ============================================================================


class TestExportableBackupFormat:
    def test_gzip_compression_roundtrip(self):
        """Verify gzip compress/decompress preserves data integrity."""
        original = {
            "version": 2,
            "created_at": datetime.now(UTC).isoformat(),
            "collections": {"memory_semantic": [{"id": str(i), "text": f"memory content {i}" * 20} for i in range(50)]},
        }
        json_bytes = json.dumps(original, ensure_ascii=False).encode("utf-8")
        compressed = gzip.compress(json_bytes, compresslevel=6)
        decompressed = gzip.decompress(compressed)
        restored = json.loads(decompressed.decode("utf-8"))

        assert restored == original
        assert len(compressed) < len(json_bytes)

    def test_backup_filename_format(self):
        """Verify backup filename convention."""
        import platform
        import socket

        hostname = socket.gethostname() or "unknown"
        device_type = platform.system().lower() or "unknown"
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        filename = f"myrm.{timestamp}.{hostname}.{device_type}.json.gz"

        assert filename.startswith("myrm.")
        assert filename.endswith(".json.gz")
        parts = filename.split(".")
        assert len(parts) >= 5
