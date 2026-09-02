"""Tests for System Storage Governance API handler functions."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.system.router import (
    CreateSnapshotRequest,
    StorageCompactionRequest,
    create_state_snapshot,
    delete_state_snapshot,
    execute_storage_compaction,
    get_storage_governance_report,
    restore_state_snapshot,
)


def test_storage_governance_api_handlers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db_path = data_dir / "data.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INT);")
        conn.execute("INSERT INTO t VALUES (1);")
        conn.commit()
        conn.close()

        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(data_dir)
        mock_disk = MagicMock(total=100_000_000_000, free=80_000_000_000, used=20_000_000_000)

        with patch("app.api.system.router.get_settings", return_value=mock_settings), \
             patch("shutil.disk_usage", return_value=mock_disk):
            # 1. get_storage_governance_report
            report = get_storage_governance_report()
            assert report.total_storage_bytes > 0
            assert len(report.categories) == 6
            assert isinstance(report.is_growth_healthy, bool)

            # 2. execute_storage_compaction
            comp_res = execute_storage_compaction(
                StorageCompactionRequest(purge_orphan_checkpoints=True, incremental_pages=100)
            )
            assert comp_res.success is True
            assert comp_res.wal_truncated is True

            # 3. create_state_snapshot
            snap_res = create_state_snapshot(CreateSnapshotRequest(label="test_handler_snapshot"))
            assert snap_res.success is True
            assert snap_res.snapshot is not None
            snap_id = snap_res.snapshot.snapshot_id

            # 4. restore_state_snapshot
            restore_res = restore_state_snapshot(snap_id)
            assert restore_res.success is True

            # 5. delete_state_snapshot
            del_res = delete_state_snapshot(snap_id)
            assert del_res.success is True
