"""Integration tests for KanbanGCService — real DB, no mocks on critical path.

Validates end-to-end GC behavior:
- events/runs deletion via real SQLite queries
- workspace directory cleanup with real filesystem
- path safety enforcement (harness_dir boundary)
- workspace_path NULL-back after cleanup
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanBoardModel,
    KanbanTaskEventModel,
    KanbanTaskModel,
    KanbanTaskRunModel,
)
from app.services.kanban.gc import KanbanGCService


def _old_dt(days: int = 60) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _fresh_dt() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex[:32]


async def _insert_board(session: AsyncSession, board_id: str) -> None:
    session.add(KanbanBoardModel(id=board_id, name="test-board", description=""))
    await session.flush()


async def _insert_task(
    session: AsyncSession, task_id: str, board_id: str,
    status: str = "archived", updated_at: datetime | None = None,
    workspace_path: str | None = None,
) -> None:
    t = KanbanTaskModel(
        id=task_id, board_id=board_id,
        title=f"task-{task_id[:8]}", description="",
        status=status, priority="normal",
        workspace_path=workspace_path,
    )
    session.add(t)
    await session.flush()
    if updated_at:
        await session.execute(
            text("UPDATE kanban_tasks SET updated_at = :ts WHERE id = :id"),
            {"ts": updated_at.strftime("%Y-%m-%d %H:%M:%S"), "id": task_id},
        )
        await session.flush()


async def _insert_event(session: AsyncSession, task_id: str, created_at: datetime | None = None) -> None:
    ev = KanbanTaskEventModel(task_id=task_id, kind="status_change")
    session.add(ev)
    await session.flush()
    if created_at:
        await session.execute(
            text("UPDATE kanban_task_events SET created_at = :ts WHERE id = :eid"),
            {"ts": created_at.strftime("%Y-%m-%d %H:%M:%S"), "eid": ev.id},
        )
        await session.flush()


async def _insert_run(session: AsyncSession, task_id: str, started_at: datetime | None = None) -> str:
    run_id = _uid()
    run = KanbanTaskRunModel(id=run_id, task_id=task_id, worker_id="test-worker")
    session.add(run)
    await session.flush()
    if started_at:
        await session.execute(
            text("UPDATE kanban_task_runs SET started_at = :ts WHERE id = :id"),
            {"ts": started_at.strftime("%Y-%m-%d %H:%M:%S"), "id": run_id},
        )
        await session.flush()
    return run_id


async def _count_events(session: AsyncSession, task_id: str) -> int:
    r = await session.execute(
        text("SELECT COUNT(*) FROM kanban_task_events WHERE task_id = :tid"),
        {"tid": task_id},
    )
    return r.scalar()


async def _count_runs(session: AsyncSession, task_id: str) -> int:
    r = await session.execute(
        text("SELECT COUNT(*) FROM kanban_task_runs WHERE task_id = :tid"),
        {"tid": task_id},
    )
    return r.scalar()


async def _get_workspace_path(session: AsyncSession, task_id: str) -> str | None:
    r = await session.execute(
        text("SELECT workspace_path FROM kanban_tasks WHERE id = :tid"),
        {"tid": task_id},
    )
    return r.scalar()


class TestGCEventsIntegration:
    """Real DB: events for terminal tasks older than retention are deleted."""

    @pytest.mark.asyncio
    async def test_deletes_old_events_preserves_fresh(self) -> None:
        board_id = _uid()
        task_done = _uid()
        task_active = _uid()

        async with get_session() as s:
            await _insert_board(s, board_id)
            await _insert_task(s, task_done, board_id, status="done")
            await _insert_task(s, task_active, board_id, status="in_progress")

            for _ in range(3):
                await _insert_event(s, task_done, _old_dt(60))
            await _insert_event(s, task_done, _fresh_dt())

            for _ in range(2):
                await _insert_event(s, task_active, _old_dt(60))

            await s.commit()

        svc = KanbanGCService()
        deleted = await svc.gc_task_events(retention_days=30)

        assert deleted == 3

        async with get_session() as s:
            assert await _count_events(s, task_done) == 1
            assert await _count_events(s, task_active) == 2

    @pytest.mark.asyncio
    async def test_archived_task_events_also_cleaned(self) -> None:
        """Events for 'archived' tasks (not just 'done') are GC'd."""
        board_id = _uid()
        task_archived = _uid()

        async with get_session() as s:
            await _insert_board(s, board_id)
            await _insert_task(s, task_archived, board_id, status="archived")

            for _ in range(3):
                await _insert_event(s, task_archived, _old_dt(60))

            await s.commit()

        svc = KanbanGCService()
        deleted = await svc.gc_task_events(retention_days=30)

        assert deleted == 3

        async with get_session() as s:
            assert await _count_events(s, task_archived) == 0

    @pytest.mark.asyncio
    async def test_backlog_task_events_not_touched(self) -> None:
        """Events for 'backlog' tasks must never be GC'd."""
        board_id = _uid()
        task_backlog = _uid()

        async with get_session() as s:
            await _insert_board(s, board_id)
            await _insert_task(s, task_backlog, board_id, status="backlog")

            for _ in range(2):
                await _insert_event(s, task_backlog, _old_dt(60))

            await s.commit()

        svc = KanbanGCService()
        deleted = await svc.gc_task_events(retention_days=30)

        assert deleted == 0

        async with get_session() as s:
            assert await _count_events(s, task_backlog) == 2


class TestGCRunsIntegration:
    """Real DB: runs for archived tasks older than retention are deleted."""

    @pytest.mark.asyncio
    async def test_deletes_old_runs_preserves_non_archived(self) -> None:
        board_id = _uid()
        task_archived = _uid()
        task_done = _uid()

        async with get_session() as s:
            await _insert_board(s, board_id)
            await _insert_task(s, task_archived, board_id, status="archived")
            await _insert_task(s, task_done, board_id, status="done")

            for _ in range(4):
                await _insert_run(s, task_archived, _old_dt(60))
            await _insert_run(s, task_archived, _fresh_dt())

            for _ in range(2):
                await _insert_run(s, task_done, _old_dt(60))

            await s.commit()

        svc = KanbanGCService()
        deleted = await svc.gc_task_runs(retention_days=30)

        assert deleted == 4

        async with get_session() as s:
            assert await _count_runs(s, task_archived) == 1
            assert await _count_runs(s, task_done) == 2


class TestGCWorkspacesIntegration:
    """Real DB + real filesystem: workspace directories are cleaned."""

    @pytest.mark.asyncio
    async def test_removes_workspace_and_nulls_path(self) -> None:
        with tempfile.TemporaryDirectory() as harness_root:
            board_id = _uid()
            task_id = _uid()

            ws_dir = Path(harness_root) / "workspaces" / task_id
            ws_dir.mkdir(parents=True)
            (ws_dir / "output.txt").write_text("result data")
            assert ws_dir.exists()

            async with get_session() as s:
                await _insert_board(s, board_id)
                await _insert_task(
                    s, task_id, board_id,
                    status="archived",
                    updated_at=_old_dt(30),
                    workspace_path=str(ws_dir),
                )
                await s.commit()

            from unittest.mock import MagicMock, patch
            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with patch("app.config.settings.settings", mock_settings):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 1
            assert freed > 0
            assert not ws_dir.exists()

            async with get_session() as s:
                assert await _get_workspace_path(s, task_id) is None

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self) -> None:
        """Workspace outside harness_dir must NOT be deleted."""
        with (
            tempfile.TemporaryDirectory() as harness_root,
            tempfile.TemporaryDirectory() as attacker_dir,
        ):
            board_id = _uid()
            task_id = _uid()

            (Path(attacker_dir) / "important.dat").write_text("do not delete")

            async with get_session() as s:
                await _insert_board(s, board_id)
                await _insert_task(
                    s, task_id, board_id,
                    status="archived",
                    updated_at=_old_dt(30),
                    workspace_path=attacker_dir,
                )
                await s.commit()

            from unittest.mock import MagicMock, patch
            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with patch("app.config.settings.settings", mock_settings):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 0
            assert freed == 0
            assert (Path(attacker_dir) / "important.dat").exists()

            async with get_session() as s:
                assert await _get_workspace_path(s, task_id) is None


    @pytest.mark.asyncio
    async def test_already_gone_workspace_nulled(self) -> None:
        """workspace_path in DB points to non-existent dir → path NULLed."""
        with tempfile.TemporaryDirectory() as harness_root:
            board_id = _uid()
            task_id = _uid()
            gone_dir = str(Path(harness_root) / "already_deleted")

            async with get_session() as s:
                await _insert_board(s, board_id)
                await _insert_task(
                    s, task_id, board_id,
                    status="archived",
                    updated_at=_old_dt(30),
                    workspace_path=gone_dir,
                )
                await s.commit()

            from unittest.mock import MagicMock, patch
            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with patch("app.config.settings.settings", mock_settings):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 0
            assert freed == 0

            async with get_session() as s:
                assert await _get_workspace_path(s, task_id) is None

    @pytest.mark.asyncio
    async def test_fresh_archived_task_workspace_not_touched(self) -> None:
        """Recently updated archived task's workspace should NOT be cleaned."""
        with tempfile.TemporaryDirectory() as harness_root:
            board_id = _uid()
            task_id = _uid()
            ws_dir = Path(harness_root) / "recent_ws"
            ws_dir.mkdir()
            (ws_dir / "data.txt").write_text("keep me")

            async with get_session() as s:
                await _insert_board(s, board_id)
                await _insert_task(
                    s, task_id, board_id,
                    status="archived",
                    updated_at=_fresh_dt(),
                    workspace_path=str(ws_dir),
                )
                await s.commit()

            from unittest.mock import MagicMock, patch
            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with patch("app.config.settings.settings", mock_settings):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 0
            assert freed == 0
            assert ws_dir.exists()

            async with get_session() as s:
                assert await _get_workspace_path(s, task_id) == str(ws_dir)

    @pytest.mark.asyncio
    async def test_done_task_workspace_not_cleaned(self) -> None:
        """Only 'archived' tasks have workspaces cleaned, not 'done'."""
        with tempfile.TemporaryDirectory() as harness_root:
            board_id = _uid()
            task_id = _uid()
            ws_dir = Path(harness_root) / "done_ws"
            ws_dir.mkdir()
            (ws_dir / "result.txt").write_text("keep")

            async with get_session() as s:
                await _insert_board(s, board_id)
                await _insert_task(
                    s, task_id, board_id,
                    status="done",
                    updated_at=_old_dt(60),
                    workspace_path=str(ws_dir),
                )
                await s.commit()

            from unittest.mock import MagicMock, patch
            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with patch("app.config.settings.settings", mock_settings):
                svc = KanbanGCService()
                deleted, freed = await svc.gc_workspaces(min_age_days=7)

            assert deleted == 0
            assert ws_dir.exists()

    @pytest.mark.asyncio
    async def test_empty_db_gc_no_error(self) -> None:
        """GC on empty (no kanban data) DB completes without error."""
        from unittest.mock import MagicMock, patch
        mock_settings = MagicMock()
        mock_settings.database.harness_dir = "/tmp/nonexistent_harness"

        with patch("app.config.settings.settings", mock_settings):
            svc = KanbanGCService()
            deleted, freed = await svc.gc_workspaces(min_age_days=7)

        assert deleted == 0
        assert freed == 0


class TestRunGCFullIntegration:
    """End-to-end: run_gc orchestrates all three GC layers."""

    @pytest.mark.asyncio
    async def test_full_gc_pass(self) -> None:
        with tempfile.TemporaryDirectory() as harness_root:
            board_id = _uid()
            t_archived = _uid()
            t_done = _uid()

            ws_dir = Path(harness_root) / "ws" / t_archived
            ws_dir.mkdir(parents=True)
            (ws_dir / "data.bin").write_bytes(b"\x00" * 256)

            async with get_session() as s:
                await _insert_board(s, board_id)
                await _insert_task(
                    s, t_archived, board_id,
                    status="archived",
                    updated_at=_old_dt(60),
                    workspace_path=str(ws_dir),
                )
                await _insert_task(s, t_done, board_id, status="done",
                                   updated_at=_old_dt(60))

                for _ in range(5):
                    await _insert_event(s, t_archived, _old_dt(60))
                    await _insert_event(s, t_done, _old_dt(60))
                for _ in range(3):
                    await _insert_run(s, t_archived, _old_dt(60))

                await s.commit()

            from unittest.mock import MagicMock, patch
            mock_settings = MagicMock()
            mock_settings.database.harness_dir = harness_root

            with patch("app.config.settings.settings", mock_settings):
                svc = KanbanGCService()
                stats = await svc.run_gc()

            assert stats.events_deleted == 10
            assert stats.runs_deleted == 3
            assert stats.workspaces_deleted == 1
            assert stats.workspace_bytes_freed >= 256
            assert stats.duration_ms > 0
            assert stats.errors == []
            assert not ws_dir.exists()

            async with get_session() as s:
                assert await _count_events(s, t_archived) == 0
                assert await _count_events(s, t_done) == 0
                assert await _count_runs(s, t_archived) == 0
                assert await _get_workspace_path(s, t_archived) is None
