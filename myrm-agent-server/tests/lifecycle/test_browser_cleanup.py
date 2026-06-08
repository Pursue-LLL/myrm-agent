"""Tests for browser lifecycle thread cleanup decoupling.

Verifies that:
1. cleanup_browser_threads works independently of warmup
2. warmup_browser_sessions is separate from cleanup
3. db_maintenance_job includes thread cleanup
4. warmup.py calls cleanup unconditionally
5. Edge cases: multiple zombies, no zombies, mark_failed failure
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestThreadCleanupDecoupling:
    """Verify thread cleanup is decoupled from browser_auto_warmup setting."""

    @pytest.mark.asyncio
    async def test_cleanup_marks_single_zombie(self):
        """Zombie threads (48h+ inactive) should be marked as failed."""
        from datetime import datetime, timedelta

        mock_record_zombie = MagicMock()
        mock_record_zombie.thread_id = "zombie-thread-1"
        mock_record_zombie.last_active_at = datetime.now() - timedelta(hours=72)

        mock_record_active = MagicMock()
        mock_record_active.thread_id = "active-thread-1"
        mock_record_active.last_active_at = datetime.now() - timedelta(hours=1)

        mock_thread_store = AsyncMock()
        mock_thread_store.find_active_threads = AsyncMock(return_value=[mock_record_zombie, mock_record_active])
        mock_thread_store.mark_failed = AsyncMock()
        mock_thread_store.cleanup_old_records = AsyncMock(return_value=3)

        mock_checkpointer = MagicMock()
        mock_checkpointer.thread_store = mock_thread_store

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

        mock_thread_store.mark_failed.assert_called_once_with("zombie-thread-1")
        mock_thread_store.cleanup_old_records.assert_called_once_with(max_age_days=7.0)

    @pytest.mark.asyncio
    async def test_cleanup_marks_multiple_zombies(self):
        """All zombie threads beyond 48h threshold should be marked failed."""
        from datetime import datetime, timedelta

        zombies = []
        for i in range(5):
            m = MagicMock()
            m.thread_id = f"zombie-{i}"
            m.last_active_at = datetime.now() - timedelta(hours=49 + i * 10)
            zombies.append(m)

        active = MagicMock()
        active.thread_id = "alive-1"
        active.last_active_at = datetime.now() - timedelta(hours=2)

        mock_thread_store = AsyncMock()
        mock_thread_store.find_active_threads = AsyncMock(return_value=[*zombies, active])
        mock_thread_store.mark_failed = AsyncMock()
        mock_thread_store.cleanup_old_records = AsyncMock(return_value=0)

        mock_checkpointer = MagicMock()
        mock_checkpointer.thread_store = mock_thread_store

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

        assert mock_thread_store.mark_failed.call_count == 5
        marked_ids = {call.args[0] for call in mock_thread_store.mark_failed.call_args_list}
        assert marked_ids == {f"zombie-{i}" for i in range(5)}

    @pytest.mark.asyncio
    async def test_cleanup_no_zombies(self):
        """When all threads are active, no mark_failed calls should occur."""
        from datetime import datetime, timedelta

        active = MagicMock()
        active.thread_id = "active-1"
        active.last_active_at = datetime.now() - timedelta(hours=1)

        mock_thread_store = AsyncMock()
        mock_thread_store.find_active_threads = AsyncMock(return_value=[active])
        mock_thread_store.mark_failed = AsyncMock()
        mock_thread_store.cleanup_old_records = AsyncMock(return_value=0)

        mock_checkpointer = MagicMock()
        mock_checkpointer.thread_store = mock_thread_store

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

        mock_thread_store.mark_failed.assert_not_called()
        mock_thread_store.cleanup_old_records.assert_called_once_with(max_age_days=7.0)

    @pytest.mark.asyncio
    async def test_cleanup_empty_thread_list(self):
        """Cleanup should handle empty active thread list gracefully."""
        mock_thread_store = AsyncMock()
        mock_thread_store.find_active_threads = AsyncMock(return_value=[])
        mock_thread_store.mark_failed = AsyncMock()
        mock_thread_store.cleanup_old_records = AsyncMock(return_value=0)

        mock_checkpointer = MagicMock()
        mock_checkpointer.thread_store = mock_thread_store

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

        mock_thread_store.mark_failed.assert_not_called()
        mock_thread_store.cleanup_old_records.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_skips_without_thread_store(self):
        """Should gracefully skip if checkpointer lacks thread_store."""
        mock_checkpointer = MagicMock(spec=[])

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

    @pytest.mark.asyncio
    async def test_cleanup_handles_get_checkpointer_exception(self):
        """Should not raise when get_checkpointer fails."""
        with patch(
            "app.platform_utils.get_checkpointer",
            side_effect=RuntimeError("DB unavailable"),
        ):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

    @pytest.mark.asyncio
    async def test_cleanup_handles_mark_failed_exception(self):
        """Should continue cleanup even if mark_failed raises for one thread."""
        from datetime import datetime, timedelta

        zombie = MagicMock()
        zombie.thread_id = "zombie-err"
        zombie.last_active_at = datetime.now() - timedelta(hours=72)

        mock_thread_store = AsyncMock()
        mock_thread_store.find_active_threads = AsyncMock(return_value=[zombie])
        mock_thread_store.mark_failed = AsyncMock(side_effect=RuntimeError("DB write failed"))
        mock_thread_store.cleanup_old_records = AsyncMock(return_value=0)

        mock_checkpointer = MagicMock()
        mock_checkpointer.thread_store = mock_thread_store

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            # Should not raise — exception is caught at the top level
            await cleanup_browser_threads()

    @pytest.mark.asyncio
    async def test_cleanup_boundary_48h_threshold(self):
        """Thread well within 48h should NOT be marked zombie; thread past 48h should."""
        from datetime import datetime, timedelta

        # 47h — safely within threshold
        safe = MagicMock()
        safe.thread_id = "safe-thread"
        safe.last_active_at = datetime.now() - timedelta(hours=47)

        # 49h — clearly past threshold
        stale = MagicMock()
        stale.thread_id = "stale-thread"
        stale.last_active_at = datetime.now() - timedelta(hours=49)

        mock_thread_store = AsyncMock()
        mock_thread_store.find_active_threads = AsyncMock(return_value=[safe, stale])
        mock_thread_store.mark_failed = AsyncMock()
        mock_thread_store.cleanup_old_records = AsyncMock(return_value=0)

        mock_checkpointer = MagicMock()
        mock_checkpointer.thread_store = mock_thread_store

        with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
            from app.lifecycle.browser import cleanup_browser_threads

            await cleanup_browser_threads()

        mock_thread_store.mark_failed.assert_called_once_with("stale-thread")

    def test_warmup_calls_cleanup_unconditionally(self):
        """warmup.py must call cleanup_browser_threads without any condition."""
        from app.server.warmup import run_async_warmup

        source = inspect.getsource(run_async_warmup)

        assert "warmup_tasks.append(cleanup_browser_threads())" in source
        assert "if settings.browser_auto_warmup:" in source
        assert "warmup_tasks.append(warmup_browser_sessions())" in source

    def test_warmup_cleanup_precedes_warmup_condition(self):
        """cleanup_browser_threads must appear BEFORE the warmup condition check."""
        from app.server.warmup import run_async_warmup

        source = inspect.getsource(run_async_warmup)
        cleanup_pos = source.index("cleanup_browser_threads()")
        warmup_cond_pos = source.index("if settings.browser_auto_warmup:")
        assert cleanup_pos < warmup_cond_pos, "cleanup must be unconditional and precede warmup condition"

    def test_warmup_initializes_browser_pool(self):
        """warmup.py must call warmup_global_browser_pool() to initialize the singleton pool with correct config."""
        from app.server.warmup import run_async_warmup

        source = inspect.getsource(run_async_warmup)
        assert "await warmup_global_browser_pool()" in source, (
            "warmup_global_browser_pool() must be awaited during startup "
            "to inject correct BrowserPoolConfig (LaunchMode.AUTO for local, defensive for sandbox) "
            "and SessionVault into web_fetch_tools"
        )

    def test_browser_pool_init_precedes_dependent_code(self):
        """warmup_global_browser_pool() must run BEFORE any code that calls get_global_browser_pool() without args."""
        from app.server.warmup import run_async_warmup

        source = inspect.getsource(run_async_warmup)
        pool_init_pos = source.index("await warmup_global_browser_pool()")
        cleanup_pos = source.index("warmup_tasks.append(cleanup_browser_threads())")
        assert pool_init_pos < cleanup_pos, (
            "warmup_global_browser_pool must run before cleanup_browser_threads "
            "to ensure the singleton pool is initialized with correct config"
        )

    def test_db_maintenance_job_includes_thread_cleanup(self):
        """db_maintenance_job must include periodic thread cleanup."""
        from app.lifecycle.schedulers import _db_maintenance_job

        source = inspect.getsource(_db_maintenance_job)
        assert "cleanup_browser_threads" in source

    def test_lifecycle_exports_all_three_functions(self):
        """__init__.py must export cleanup, warmup, and backward-compat functions."""
        from app.lifecycle import (
            cleanup_and_warmup_browser_threads,
            cleanup_browser_threads,
            warmup_browser_sessions,
        )

        assert callable(cleanup_browser_threads)
        assert callable(warmup_browser_sessions)
        assert callable(cleanup_and_warmup_browser_threads)

    @pytest.mark.asyncio
    async def test_backward_compat_calls_both(self):
        """cleanup_and_warmup_browser_threads calls both functions in order."""
        with (
            patch("app.lifecycle.browser.cleanup_browser_threads", new_callable=AsyncMock) as mock_cleanup,
            patch("app.lifecycle.browser.warmup_browser_sessions", new_callable=AsyncMock) as mock_warmup,
        ):
            from app.lifecycle.browser import cleanup_and_warmup_browser_threads

            await cleanup_and_warmup_browser_threads()

            mock_cleanup.assert_called_once()
            mock_warmup.assert_called_once()
