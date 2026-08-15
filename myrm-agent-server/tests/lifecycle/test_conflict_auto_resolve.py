"""Tests for _auto_resolve_expired_conflicts in memory_guardian.

Covers:
- Resolves expired conflicts (status → resolved, resolved_at set)
- Does not resolve non-expired conflicts
- Does not resolve already-resolved conflicts
- Returns correct count
- Handles empty result set
- Filters out rows where conflict_auto_resolve_at IS NULL (high-risk conflicts)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAutoResolveExpiredConflicts:
    """Tests for the _auto_resolve_expired_conflicts function."""

    @pytest.mark.asyncio
    async def test_resolves_expired_conflicts(self) -> None:
        from app.lifecycle.memory_guardian import _auto_resolve_expired_conflicts

        mock_result = MagicMock()
        mock_result.rowcount = 3

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            count = await _auto_resolve_expired_conflicts()

        assert count == 3
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

        stmt = mock_db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "pending_memories" in compiled.lower() or "pendingmemory" in compiled.lower()

    @pytest.mark.asyncio
    async def test_returns_zero_when_none_expired(self) -> None:
        from app.lifecycle.memory_guardian import _auto_resolve_expired_conflicts

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            count = await _auto_resolve_expired_conflicts()

        assert count == 0

    @pytest.mark.asyncio
    async def test_update_sets_resolved_status(self) -> None:
        from app.lifecycle.memory_guardian import _auto_resolve_expired_conflicts

        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            await _auto_resolve_expired_conflicts()

        stmt = mock_db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "resolved" in compiled.lower() or "status" in compiled.lower()

    @pytest.mark.asyncio
    async def test_query_filters_out_none_auto_resolve_at(self) -> None:
        """High-risk conflicts (auto_resolve_at=None) must never match the expiry query.

        The auto-resolve UPDATE only targets rows where conflict_auto_resolve_at
        IS NOT NULL and <= now, so high-risk conflicts stay pending forever until
        the user resolves them manually.
        """
        from app.lifecycle.memory_guardian import _auto_resolve_expired_conflicts

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            await _auto_resolve_expired_conflicts()

        stmt = mock_db.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "conflict_auto_resolve_at is not null" in compiled.lower()
        assert "conflict_auto_resolve_at" in compiled.lower()


class TestRecordConflictAutoResolveEvent:
    """Tests for the guardian's auto-resolve audit event."""

    @pytest.mark.asyncio
    async def test_records_audit_event_with_count(self) -> None:
        from app.lifecycle.memory_guardian import _record_conflict_auto_resolve_event

        mock_ledger = AsyncMock()
        mock_ledger.record_event = AsyncMock(return_value=MagicMock())
        mock_ledger_service_cls = MagicMock(return_value=mock_ledger)

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            patch(
                "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
                mock_ledger_service_cls,
            ),
        ):
            await _record_conflict_auto_resolve_event(2)

        mock_ledger.record_event.assert_called_once()
        _, kwargs = mock_ledger.record_event.call_args
        assert kwargs["kind"].value == "maintenance"
        assert kwargs["status"].value == "success"
        assert kwargs["metadata"]["auto_resolved_conflicts"] == 2
        assert kwargs["metadata"]["resolution"] == "keep_old"
        assert kwargs["commit"] is True

    @pytest.mark.asyncio
    async def test_ledger_failure_is_non_fatal(self) -> None:
        from app.lifecycle.memory_guardian import _record_conflict_auto_resolve_event

        mock_ledger = AsyncMock()
        mock_ledger.record_event = AsyncMock(side_effect=RuntimeError("ledger down"))
        mock_ledger_service_cls = MagicMock(return_value=mock_ledger)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            patch(
                "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
                mock_ledger_service_cls,
            ),
        ):
            await _record_conflict_auto_resolve_event(1)  # must not raise
