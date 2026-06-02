"""Tests for cleanup_qdrant_locks script.

Covers:
- _get_default_qdrant_path: default path resolution from MYRM_DATA_DIR
- cleanup_qdrant_locks: lock file cleanup logic
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from scripts.cleanup_qdrant_locks import _get_default_qdrant_path, cleanup_qdrant_locks


class TestGetDefaultQdrantPath:
    """Tests for _get_default_qdrant_path helper."""

    def test_returns_myrm_data_dir_qdrant(self):
        """Verify qdrant path is MYRM_DATA_DIR/qdrant when env var is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MYRM_DATA_DIR": str(tmpdir)}):
                result = _get_default_qdrant_path()
                assert result == str(Path(tmpdir) / "qdrant")

    def test_returns_home_myrm_qdrant_default(self):
        """Verify default qdrant path is ~/.myrm/qdrant when MYRM_DATA_DIR is not set."""
        env_copy = os.environ.copy()
        env_copy.pop("MYRM_DATA_DIR", None)
        with patch.dict(os.environ, env_copy, clear=True):
            result = _get_default_qdrant_path()
            assert result == str(Path.home() / ".myrm" / "qdrant")


class TestCleanupQdrantLocks:
    """Tests for cleanup_qdrant_locks function."""

    def test_removes_old_lock_files(self):
        """Verify old .lock files are removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a lock file with old timestamp
            lock_file = Path(tmpdir) / ".lock"
            lock_file.write_text("test")
            # Set modification time to 60 seconds ago
            old_time = time.time() - 60
            os.utime(lock_file, (old_time, old_time))

            result = cleanup_qdrant_locks(base_path=tmpdir, max_age_seconds=30)
            assert result == 1
            assert not lock_file.exists()

    def test_keeps_recent_lock_files(self):
        """Verify recent .lock files are kept."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a lock file with recent timestamp
            lock_file = Path(tmpdir) / ".lock"
            lock_file.write_text("test")

            result = cleanup_qdrant_locks(base_path=tmpdir, max_age_seconds=30)
            assert result == 0
            assert lock_file.exists()

    def test_handles_missing_directory(self):
        """Verify cleanup handles missing directory gracefully."""
        result = cleanup_qdrant_locks(base_path="/nonexistent/path", max_age_seconds=30)
        assert result == 0

    def test_handles_empty_directory(self):
        """Verify cleanup handles empty directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cleanup_qdrant_locks(base_path=tmpdir, max_age_seconds=30)
            assert result == 0

    def test_ignores_non_lock_files(self):
        """Verify non-.lock files are not removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a non-lock file with old timestamp
            other_file = Path(tmpdir) / "data.db"
            other_file.write_text("test")
            old_time = time.time() - 60
            os.utime(other_file, (old_time, old_time))

            result = cleanup_qdrant_locks(base_path=tmpdir, max_age_seconds=30)
            assert result == 0
            assert other_file.exists()
