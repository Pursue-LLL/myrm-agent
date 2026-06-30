"""Tests for create_conflict_callback factory.

Covers:
- Callback returns ConflictResolution.PENDING on success
- Callback falls back to ConflictResolution.KEEP_OLD on DB error
- PendingMemory record fields are populated correctly
- agent_id is captured in closure
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.memory.strategies.consolidation import ConflictContext
from myrm_agent_harness.toolkits.memory.types import ConflictResolution


class TestCreateConflictCallback:
    """Tests for the create_conflict_callback factory function."""

    @pytest.mark.asyncio
    async def test_returns_pending_on_success(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-mem-1",
            old_content="Python is best",
            new_content="Rust is better",
            accuracy_score=0.7,
            importance=0.8,
            merge_suggestion="Both have merits",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            result = await callback(ctx)

        assert result == ConflictResolution.PENDING
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        record = mock_db.add.call_args[0][0]
        assert record.is_conflict is True
        assert record.conflict_old_memory_id == "old-mem-1"
        assert record.conflict_old_content == "Python is best"
        assert record.content == "Rust is better"
        assert record.conflict_accuracy_score == 0.7
        assert record.conflict_importance == 0.8
        assert record.agent_id == "agent-1"
        assert record.status == "pending"
        assert record.memory_type == "semantic"
        assert record.metadata_json["merge_suggestion"] == "Both have merits"
        assert record.metadata_json["source"] == "consolidation_conflict"

    @pytest.mark.asyncio
    async def test_auto_resolve_at_set_72h(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.9,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        before = datetime.now(UTC)
        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            await callback(ctx)
        after = datetime.now(UTC)

        record = mock_db.add.call_args[0][0]
        assert record.conflict_auto_resolve_at is not None
        expected_min = before + timedelta(hours=72)
        expected_max = after + timedelta(hours=72)
        assert expected_min <= record.conflict_auto_resolve_at <= expected_max

    @pytest.mark.asyncio
    async def test_falls_back_to_keep_old_on_db_error(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.9,
            merge_suggestion="c",
        )

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            result = await callback(ctx)

        assert result == ConflictResolution.KEEP_OLD

    @pytest.mark.asyncio
    async def test_none_agent_id(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id=None)
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.9,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.connection.get_session", return_value=mock_session_ctx):
            result = await callback(ctx)

        assert result == ConflictResolution.PENDING
        record = mock_db.add.call_args[0][0]
        assert record.agent_id is None
