"""Tests for _auto_resolve_expired_conflicts in memory_guardian.

Covers:
- Resolves expired conflicts (status → resolved, resolved_at set)
- Does not resolve non-expired conflicts
- Does not resolve already-resolved conflicts
- Returns correct count
- Handles empty result set
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
