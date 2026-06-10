"""Unit tests for KanbanGCService."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.kanban.gc import (
    GCStats,
    KanbanGCService,
    _cutoff_iso,
    _dir_size_bytes,
)


class TestGCStats:
    def test_defaults(self) -> None:
        stats = GCStats()
        assert stats.events_deleted == 0
        assert stats.runs_deleted == 0
        assert stats.workspaces_deleted == 0
        assert stats.workspace_bytes_freed == 0
        assert stats.duration_ms == 0.0
        assert stats.errors == []

    def test_error_list_independence(self) -> None:
        """Ensure default factory creates independent lists."""
        a = GCStats()
        b = GCStats()
        a.errors.append("x")
        assert b.errors == []


class TestCutoffIso:
    def test_format(self) -> None:
        result = _cutoff_iso(30)
        assert len(result) == 19
        assert result[4] == "-"
        assert result[10] == " "

    def test_different_days(self) -> None:
        r1 = _cutoff_iso(1)
        r30 = _cutoff_iso(30)
        assert r1 > r30


class TestDirSizeBytes:
    def test_existing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "a.txt").write_text("hello")
            (p / "b.txt").write_text("world!")
            size = _dir_size_bytes(p)
            assert size == 11

    def test_nonexistent_dir(self) -> None:
        assert _dir_size_bytes(Path("/nonexistent_path_abc123")) == 0

    def test_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            assert _dir_size_bytes(Path(td)) == 0


class TestGCTaskEvents:
    @pytest.mark.asyncio
    async def test_deletes_in_batches(self) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.kanban.gc.get_session", return_value=mock_ctx):
            svc = KanbanGCService()
            deleted = await svc.gc_task_events(retention_days=30)

        assert deleted == 0
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_batches(self) -> None:
        """Verify loop continues when batch is full."""
        mock_result_full = MagicMock()
        mock_result_full.rowcount = 1000

        mock_result_partial = MagicMock()
        mock_result_partial.rowcount = 50

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_full, mock_result_partial])
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.kanban.gc.get_session", return_value=mock_ctx):
            svc = KanbanGCService()
            deleted = await svc.gc_task_events(retention_days=30)

        assert deleted == 1050
        assert mock_session.execute.call_count == 2


class TestGCTaskRuns:
    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.kanban.gc.get_session", return_value=mock_ctx):
            svc = KanbanGCService()
            deleted = await svc.gc_task_runs(retention_days=30)

        assert deleted == 0


class TestGCWorkspaces:
    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[])

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.database.harness_dir = "/tmp/harness_test"

        with (
            patch("app.services.kanban.gc.get_session", return_value=mock_ctx),
            patch("app.services.kanban.gc.settings", mock_settings, create=True),
            patch("app.config.settings.settings", mock_settings),
        ):
            svc = KanbanGCService()
            deleted, freed = await svc.gc_workspaces(min_age_days=7)

        assert deleted == 0
        assert freed == 0

    @pytest.mark.asyncio
    async def test_removes_directory_and_nulls_path(self) -> None:
        with tempfile.TemporaryDirectory() as harness_root:
            ws_dir = Path(harness_root) / "task_abc" / "workspace"
            ws_dir.mkdir(parents=True)
            (ws_dir / "file.txt").write_text("data")

            task_id = "task-abc-12345678"
            select_result = MagicMock()
            select_result.fetchall = MagicMock(return_value=[(task_id, str(ws_dir))])

            update_result = MagicMock()
            update_result.rowcount = 1

            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=[select_result, update_result])
            mock_session.commit = AsyncMock()

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with (
                patch("app.services.kanban.gc.get_session", return_value=mock_ctx),
                patch("app.config.settings.settings", mock_settings),
            ):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 1
            assert freed > 0
            assert not ws_dir.exists()
            assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_outside_harness_root(self) -> None:
        """Workspace path outside harness_dir should be skipped and NULLed."""
        with tempfile.TemporaryDirectory() as harness_root, tempfile.TemporaryDirectory() as outside_dir:
            task_id = "task-outside-1234"
            select_result = MagicMock()
            select_result.fetchall = MagicMock(return_value=[(task_id, outside_dir)])

            update_result = MagicMock()

            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=[select_result, update_result])
            mock_session.commit = AsyncMock()

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)

            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with (
                patch("app.services.kanban.gc.get_session", return_value=mock_ctx),
                patch("app.config.settings.settings", mock_settings),
            ):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 0
            assert freed == 0
            assert Path(outside_dir).exists()


class TestRunGC:
    @pytest.mark.asyncio
    async def test_run_gc_orchestration(self) -> None:
        svc = KanbanGCService()

        with (
            patch.object(svc, "gc_task_events", new_callable=AsyncMock, return_value=10),
            patch.object(svc, "gc_task_runs", new_callable=AsyncMock, return_value=5),
            patch.object(svc, "gc_workspaces", new_callable=AsyncMock, return_value=(2, 1024)),
        ):
            stats = await svc.run_gc()

        assert stats.events_deleted == 10
        assert stats.runs_deleted == 5
        assert stats.workspaces_deleted == 2
        assert stats.workspace_bytes_freed == 1024
        assert stats.duration_ms > 0
        assert stats.errors == []

    @pytest.mark.asyncio
    async def test_run_gc_isolates_errors(self) -> None:
        svc = KanbanGCService()

        with (
            patch.object(svc, "gc_task_events", new_callable=AsyncMock, side_effect=RuntimeError("db err")),
            patch.object(svc, "gc_task_runs", new_callable=AsyncMock, return_value=3),
            patch.object(svc, "gc_workspaces", new_callable=AsyncMock, return_value=(0, 0)),
        ):
            stats = await svc.run_gc()

        assert stats.events_deleted == 0
        assert stats.runs_deleted == 3
        assert len(stats.errors) == 1
        assert "events" in stats.errors[0]
