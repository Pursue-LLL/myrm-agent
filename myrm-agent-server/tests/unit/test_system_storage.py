"""Unit tests for GET /api/v1/system/storage endpoint."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.system.router import StorageInfoResponse, _dir_size_bytes, get_storage_info


class TestDirSizeBytes:
    """Tests for _dir_size_bytes helper."""

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        assert _dir_size_bytes(tmp_path / "nonexistent") == 0

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _dir_size_bytes(tmp_path) == 0

    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"x" * 100)
        assert _dir_size_bytes(tmp_path) == 100

    def test_nested_files(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_bytes(b"x" * 50)
        (sub / "b.txt").write_bytes(b"x" * 30)
        assert _dir_size_bytes(tmp_path) == 80

    def test_file_path_returns_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_bytes(b"data")
        assert _dir_size_bytes(f) == 0


class TestGetStorageInfo:
    """Tests for get_storage_info route handler."""

    def test_returns_storage_info(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "data.db").write_bytes(b"d" * 500)
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(data_dir)

        with patch("app.api.system.router.get_settings", return_value=mock_settings):
            result = get_storage_info()

        assert isinstance(result, StorageInfoResponse)
        assert result.data_dir == str(data_dir)
        assert result.disk_total_bytes > 0
        assert result.disk_free_bytes > 0
        assert result.disk_used_bytes > 0

    def test_includes_data_db(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "data.db").write_bytes(b"d" * 500)
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(data_dir)

        with patch("app.api.system.router.get_settings", return_value=mock_settings):
            result = get_storage_info()

        db_entries = [s for s in result.subdirs if s.name == "data.db"]
        assert len(db_entries) == 1
        assert db_entries[0].bytes == 500

    def test_includes_existing_subdirs(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        (data_dir / "qdrant").mkdir(parents=True)
        (data_dir / "qdrant" / "vectors.bin").write_bytes(b"v" * 200)
        (data_dir / "harness").mkdir(parents=True)
        (data_dir / "data.db").write_bytes(b"d" * 500)
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(data_dir)

        with patch("app.api.system.router.get_settings", return_value=mock_settings):
            result = get_storage_info()

        names = [s.name for s in result.subdirs]
        assert "qdrant" in names
        assert "harness" in names

    def test_excludes_nonexistent_subdirs(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(data_dir)

        with patch("app.api.system.router.get_settings", return_value=mock_settings):
            result = get_storage_info()

        names = [s.name for s in result.subdirs]
        assert "event_logs" not in names
        assert "memory" not in names

    def test_nonexistent_data_dir_uses_parent(self, tmp_path: Path) -> None:
        fake_dir = tmp_path / "nonexistent_child"
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(fake_dir)

        with patch("app.api.system.router.get_settings", return_value=mock_settings):
            result = get_storage_info()

        assert result.disk_total_bytes > 0
        assert result.subdirs == []

    def test_is_sync_function(self) -> None:
        """Verify get_storage_info is a regular (sync) function, not async."""
        assert not asyncio.iscoroutinefunction(get_storage_info)
