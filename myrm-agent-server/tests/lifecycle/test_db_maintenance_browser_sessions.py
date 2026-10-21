"""The 6-hourly database maintenance job sweeps expired saved browser sessions."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.lifecycle.schedulers import _db_maintenance_job


@pytest.mark.asyncio
async def test_db_maintenance_job_sweeps_expired_browser_sessions() -> None:
    with (
        patch("app.core.security.browser_vault.cleanup_all_vaults", new_callable=AsyncMock, return_value=2) as sweep,
        patch("app.platform_utils.session_factory"),
        patch("app.database.operations.backup.get_sqlite_backup_manager", return_value=None),
        patch("app.lifecycle.schedulers.logger"),
    ):
        await _db_maintenance_job()

    sweep.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_db_maintenance_job_survives_a_failing_browser_session_sweep() -> None:
    with (
        patch(
            "app.core.security.browser_vault.cleanup_all_vaults", new_callable=AsyncMock, side_effect=OSError("vault unreadable")
        ),
        patch("app.platform_utils.session_factory"),
        patch("app.database.operations.backup.get_sqlite_backup_manager", return_value=None),
        patch("app.lifecycle.schedulers.logger") as logger,
    ):
        await _db_maintenance_job()

    assert any("Browser session GC failed" in str(call.args[0]) for call in logger.warning.call_args_list)
