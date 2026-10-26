"""Cloud Backup Remote integration tests.

Tests core backup remote modules:
- backup_remote.py: Strategy, config dataclasses, XML parsing
- backup_remote_scheduler.py: _upload_with_retry, _rotate_backups, the run/restore guards
- API endpoints: check-connection, trigger, list, restore, delete
(the snapshot round trip lives in tests/services/memory/backup/)
"""

from __future__ import annotations

import gzip
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.in_memory_remote_backup import InMemoryBackupStrategy
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")
from app.api.memory.utils import get_crud_memory_manager
from app.services.memory.backup.backup_remote import (
    RemoteBackupFile,
    S3BackupConfig,
    WebDAVBackupConfig,
    _parse_webdav_multistatus,
)

client = TestClient(app)


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

    def test_parse_returns_names_as_they_were_uploaded(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/myrm-backups/myrm.20260101000000.%E5%B0%8F%E6%98%8E.linux.json.gz</d:href>
    <d:propstat><d:prop><d:getcontentlength>10</d:getcontentlength></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>http://dav.example.com/myrm-backups/myrm.20260101000000.my%20laptop.linux.json.gz</d:href>
    <d:propstat><d:prop><d:getcontentlength>10</d:getcontentlength></d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        names = [f.file_name for f in _parse_webdav_multistatus(xml)]
        assert names == ["myrm.20260101000000.小明.linux.json.gz", "myrm.20260101000000.my laptop.linux.json.gz"]

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
        from app.services.memory.backup.backup_remote_scheduler import _upload_with_retry

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
        from app.services.memory.backup.backup_remote_scheduler import _upload_with_retry

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
        from app.services.memory.backup.backup_remote_scheduler import _upload_with_retry

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
        import app.services.memory.backup.backup_remote_scheduler as sched

        original = sched._auto_backup_running
        sched._auto_backup_running = True

        strategy = InMemoryBackupStrategy()
        result = await sched.run_remote_backup(manager=MagicMock(), strategy=strategy, device_name="test")
        assert result["success"] is False
        assert "already in progress" in str(result.get("error", "")).lower()

        sched._auto_backup_running = original


# ============================================================================
# Tests: Backup Rotation
# ============================================================================


class TestBackupRotation:
    @pytest.mark.asyncio
    async def test_rotation_deletes_old_backups(self):
        from app.services.memory.backup.backup_remote_scheduler import _rotate_backups

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
        from app.services.memory.backup.backup_remote_scheduler import _rotate_backups

        strategy = InMemoryBackupStrategy()
        strategy._storage["myrm.20250101120000.host.linux.json.gz"] = b"data"
        strategy._storage["myrm.20250102120000.host.linux.json.gz"] = b"data"

        await _rotate_backups(strategy, "host", "linux", max_backups=5)

        files = await strategy.list_files()
        assert len(files) == 2


# ============================================================================
# Tests: Restore from Remote
# ============================================================================


class TestRestoreFromRemote:
    @pytest.mark.asyncio
    async def test_restore_fails_on_download_error(self):
        from app.services.memory.backup.backup_remote_scheduler import restore_from_remote

        strategy = InMemoryBackupStrategy()
        result = await restore_from_remote(
            manager=MagicMock(),
            strategy=strategy,
            file_name="nonexistent.json.gz",
        )
        assert result["success"] is False
        assert "download" in str(result.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_restore_fails_on_invalid_version(self):
        from app.services.memory.backup.backup_remote_scheduler import restore_from_remote

        strategy = InMemoryBackupStrategy()
        backup_data = {"version": 1, "collections": {}}
        compressed = gzip.compress(json.dumps(backup_data).encode())
        strategy._storage["old_backup.json.gz"] = compressed

        result = await restore_from_remote(
            manager=MagicMock(),
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
        app.dependency_overrides[get_crud_memory_manager] = lambda: MagicMock()
        try:
            with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
                yield
        finally:
            app.dependency_overrides.pop(get_crud_memory_manager, None)

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
