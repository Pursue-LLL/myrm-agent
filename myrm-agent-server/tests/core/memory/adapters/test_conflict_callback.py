"""Tests for create_conflict_callback factory.

Covers:
- Callback returns ConflictResolution.PENDING on success
- Callback falls back to ConflictResolution.KEEP_OLD on DB error
- PendingMemory record fields are populated correctly
- agent_id is captured in closure
- Low-risk conflicts (importance < 0.9) get a 72h auto_resolve_at deadline
- High-risk conflicts (importance >= 0.9) keep auto_resolve_at None (never auto-resolve)
- Boundary: importance 0.9 is high-risk, 0.89 is not
- None importance is treated as low-risk (safe default)
- Ledger event is recorded on success and its failure is non-fatal
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.strategies.consolidation import ConflictContext
from myrm_agent_harness.toolkits.memory.types import ConflictResolution


@contextmanager
def _mock_ledger_service() -> AsyncMock:
    """Isolate conflict tests from the (parallel-added) ledger publishing step.

    The conflict callback now also records a ledger event after persistence; tests
    that only want to inspect the PendingMemory record must stub the ledger service
    so it does not issue its own db.add on the shared mock session.
    """
    mock_ledger = AsyncMock()
    mock_ledger.record_event = AsyncMock()
    with patch(
        "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
        return_value=mock_ledger,
    ):
        yield mock_ledger


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

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
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
    async def test_auto_resolve_at_set_72h_for_low_risk(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.85,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        before = datetime.now(UTC)
        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
            await callback(ctx)
        after = datetime.now(UTC)

        record = mock_db.add.call_args[0][0]
        assert record.conflict_auto_resolve_at is not None
        expected_min = before + timedelta(hours=72)
        expected_max = after + timedelta(hours=72)
        assert expected_min <= record.conflict_auto_resolve_at <= expected_max

    @pytest.mark.asyncio
    async def test_high_risk_importance_keeps_auto_resolve_at_none(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.95,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
            result = await callback(ctx)

        assert result == ConflictResolution.PENDING
        record = mock_db.add.call_args[0][0]
        assert record.conflict_importance == 0.95
        assert record.conflict_auto_resolve_at is None

    @pytest.mark.asyncio
    async def test_importance_boundary_0_9_is_high_risk(self) -> None:
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

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
            await callback(ctx)

        record = mock_db.add.call_args[0][0]
        assert record.conflict_auto_resolve_at is None

    @pytest.mark.asyncio
    async def test_importance_below_0_9_keeps_auto_resolve(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.89,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
            await callback(ctx)

        record = mock_db.add.call_args[0][0]
        assert record.conflict_auto_resolve_at is not None

    @pytest.mark.asyncio
    async def test_none_importance_is_not_high_risk(self) -> None:
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=None,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
            await callback(ctx)

        record = mock_db.add.call_args[0][0]
        assert record.conflict_auto_resolve_at is not None

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
    async def test_records_ledger_event_on_success(self) -> None:
        """Conflict persistence must also publish a ledger event (SSE badge refresh)."""
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-mem-1",
            old_content="Python is best",
            new_content="Rust is better",
            accuracy_score=0.7,
            importance=0.95,
            merge_suggestion="Both have merits",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_ledger_service = AsyncMock()
        mock_ledger_service.record_event = AsyncMock()
        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            patch(
                "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
                return_value=mock_ledger_service,
            ),
        ):
            result = await callback(ctx)

        assert result == ConflictResolution.PENDING
        mock_ledger_service.record_event.assert_awaited_once()
        kwargs = mock_ledger_service.record_event.await_args.kwargs
        assert kwargs["kind"].value == "conflict"
        assert kwargs["target_id"] == mock_db.add.call_args[0][0].id
        assert kwargs["commit"] is True
        assert kwargs["metadata"] == {"high_risk": True}
        assert "importance=" not in kwargs["summary"]
        assert "old_memory" not in kwargs["summary"]

    @pytest.mark.asyncio
    async def test_ledger_event_failure_does_not_break_persistence(self) -> None:
        """Ledger publish failure must be non-fatal (conflict still persisted as PENDING)."""
        from app.core.memory.adapters.setup import create_conflict_callback

        callback = create_conflict_callback(agent_id="agent-1")
        ctx = ConflictContext(
            old_memory_id="old-mem-1",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.95,
            merge_suggestion="c",
        )

        mock_db = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            patch(
                "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
                side_effect=RuntimeError("ledger down"),
            ),
        ):
            result = await callback(ctx)

        assert result == ConflictResolution.PENDING
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

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

        with (
            patch("app.database.connection.get_session", return_value=mock_session_ctx),
            _mock_ledger_service(),
        ):
            result = await callback(ctx)

        assert result == ConflictResolution.PENDING
        record = mock_db.add.call_args[0][0]
        assert record.agent_id is None
