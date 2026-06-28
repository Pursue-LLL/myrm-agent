"""Integration test for ApprovalRegistry.resolve_approval idempotency.

Verifies the PENDING-only guard in resolve_approval using a real SQLite
in-memory database (no mocks on the data path).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base


_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@asynccontextmanager
async def _test_get_session() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture(autouse=True)
def _patch_session():
    with patch(
        "app.services.approvals.registry.get_session",
        _test_get_session,
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_event_bus():
    from unittest.mock import MagicMock

    mock_bus = MagicMock()
    with patch(
        "app.services.approvals.registry.get_event_bus",
        return_value=mock_bus,
    ):
        yield


@pytest.fixture(autouse=True, scope="module")
def _create_tables():
    async def _setup():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_setup())
    yield
    async def _teardown():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await _engine.dispose()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_teardown())


async def _seed_record(status: str = "PENDING") -> str:
    record_id = "test-resolve-idempotency"
    async with _test_get_session() as db:
        existing = await db.get(ApprovalRecord, record_id)
        if existing:
            await db.delete(existing)
            await db.commit()

        record = ApprovalRecord(
            id=record_id,
            agent_id="agent-1",
            chat_id="chat-1",
            thread_id="thread-1",
            action_type="shell_command",
            reason="test",
            severity="warning",
            payload={"cmd": "ls"},
            status=status,
        )
        db.add(record)
        await db.commit()
    return record_id


class TestResolveApprovalIdempotency:
    """Validates that resolve_approval only processes PENDING records."""

    @pytest.mark.asyncio
    async def test_first_resolve_succeeds(self):
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("PENDING")
        result = await ApprovalRegistry.resolve_approval(record_id, "approve")

        assert result is not None
        assert result.status == "APPROVED"
        assert result.resolved_at is not None

    @pytest.mark.asyncio
    async def test_duplicate_resolve_returns_none(self):
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("PENDING")
        first = await ApprovalRegistry.resolve_approval(record_id, "approve")
        assert first is not None
        assert first.status == "APPROVED"

        second = await ApprovalRegistry.resolve_approval(record_id, "deny")
        assert second is None

    @pytest.mark.asyncio
    async def test_resolve_already_rejected_returns_none(self):
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("PENDING")
        first = await ApprovalRegistry.resolve_approval(record_id, "deny")
        assert first is not None
        assert first.status == "REJECTED"

        second = await ApprovalRegistry.resolve_approval(record_id, "approve")
        assert second is None

    @pytest.mark.asyncio
    async def test_status_not_flipped_after_duplicate(self):
        """The critical data-integrity scenario: REJECTED must not become APPROVED."""
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("PENDING")
        await ApprovalRegistry.resolve_approval(record_id, "deny")
        await ApprovalRegistry.resolve_approval(record_id, "approve")

        async with _test_get_session() as db:
            record = await db.get(ApprovalRecord, record_id)
            assert record is not None
            assert record.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_returns_none(self):
        from app.services.approvals.registry import ApprovalRegistry

        result = await ApprovalRegistry.resolve_approval("nonexistent-id", "approve")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_timeout_record_returns_none(self):
        """TIMEOUT records should not be resolvable."""
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("TIMEOUT")
        result = await ApprovalRegistry.resolve_approval(record_id, "approve")
        assert result is None

    @pytest.mark.asyncio
    async def test_edited_payload_merged_on_approve(self):
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("PENDING")
        result = await ApprovalRegistry.resolve_approval(
            record_id, "approve", edited_payload={"cmd": "echo hi"}
        )

        assert result is not None
        assert result.payload["cmd"] == "echo hi"

    @pytest.mark.asyncio
    async def test_resolved_at_is_set(self):
        from app.services.approvals.registry import ApprovalRegistry

        record_id = await _seed_record("PENDING")
        result = await ApprovalRegistry.resolve_approval(record_id, "approve")

        assert result is not None
        assert result.resolved_at is not None
