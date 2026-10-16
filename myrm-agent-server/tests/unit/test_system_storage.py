"""Unit tests for GET /api/v1/system/storage endpoint."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.system.router import get_storage_info
from app.api.system.schemas import StorageInfoResponse


def _storage_info(data_dir: Path) -> StorageInfoResponse:
    mock_settings = MagicMock()
    mock_settings.database.state_dir = str(data_dir)
    with patch("app.api.system.router.get_settings", return_value=mock_settings):
        return get_storage_info()


class TestGetStorageInfo:
    """Tests for get_storage_info route handler."""

    def test_returns_storage_info(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "data.db").write_bytes(b"d" * 500)

        result = _storage_info(data_dir)

        assert isinstance(result, StorageInfoResponse)
        assert result.data_dir == str(data_dir)
        assert result.disk_total_bytes > 0
        assert result.disk_free_bytes > 0
        assert result.disk_used_bytes > 0

    def test_reports_the_state_database_with_its_log_files(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "data.db").write_bytes(b"d" * 500)
        (data_dir / "data.db-wal").write_bytes(b"w" * 20)
        (data_dir / "data.db-shm").write_bytes(b"s" * 10)

        breakdown = _storage_info(data_dir).db_breakdown

        assert (breakdown.main_db_bytes, breakdown.wal_bytes, breakdown.shm_bytes) == (500, 20, 10)
        assert breakdown.total_bytes == 530

    def test_a_data_directory_without_a_database_reports_no_database_bytes(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        assert _storage_info(data_dir).db_breakdown.total_bytes == 0

    def test_nonexistent_data_dir_uses_parent(self, tmp_path: Path) -> None:
        result = _storage_info(tmp_path / "nonexistent_child")

        assert result.disk_total_bytes > 0
        assert result.db_breakdown.total_bytes == 0

    def test_is_sync_function(self) -> None:
        """Verify get_storage_info is a regular (sync) function, not async."""
        assert not asyncio.iscoroutinefunction(get_storage_info)
