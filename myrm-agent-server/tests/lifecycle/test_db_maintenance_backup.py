"""The periodic database backup copies and verifies the whole image; it must not run on the event loop."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

from app.lifecycle.schedulers import _db_maintenance_job


async def test_the_periodic_backup_runs_on_a_worker_thread() -> None:
    loop_thread = threading.get_ident()
    backup_threads: list[int] = []
    manager = MagicMock()
    manager.create_backup.side_effect = lambda: backup_threads.append(threading.get_ident())

    with (
        patch("app.database.operations.backup.get_sqlite_backup_manager", return_value=manager),
        patch("app.platform_utils.session_factory"),
        patch("app.lifecycle.schedulers.maintenance.logger"),
    ):
        await _db_maintenance_job()

    assert len(backup_threads) == 1
    assert backup_threads[0] != loop_thread


async def test_a_failing_backup_is_logged_and_the_remaining_sweeps_still_run() -> None:
    manager = MagicMock()
    manager.create_backup.side_effect = OSError("disk full")

    with (
        patch("app.database.operations.backup.get_sqlite_backup_manager", return_value=manager),
        patch("app.core.security.browser_vault.cleanup_all_vaults", new_callable=AsyncMock, return_value=0) as sweep,
        patch("app.platform_utils.session_factory"),
        patch("app.lifecycle.schedulers.maintenance.logger") as logger,
    ):
        await _db_maintenance_job()

    assert any("Periodic database backup failed" in str(call.args[0]) for call in logger.warning.call_args_list)
    sweep.assert_awaited_once_with()
