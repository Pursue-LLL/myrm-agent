"""Tests for System Storage Governance API handler functions."""

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
        (data_dir / "data.db").write_bytes(b"dummy_data_content")

        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(data_dir)

        with patch("app.api.system.router.get_settings", return_value=mock_settings):
            # 1. get_storage_governance_report
            report = get_storage_governance_report()
            assert report.total_storage_bytes > 0
            assert len(report.categories) == 6
            assert report.is_growth_healthy is True

            # 2. execute_storage_compaction
            comp_res = execute_storage_compaction(StorageCompactionRequest(purge_orphan_checkpoints=True, incremental_pages=100))
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
