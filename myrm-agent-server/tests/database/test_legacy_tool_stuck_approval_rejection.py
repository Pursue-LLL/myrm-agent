"""A loop-guard pause is not an approval; a leftover PENDING row of that type is closed once, and only such rows are.

Such a row has no expiry, so no sweep reaches it, and the chat it belongs to refuses every new message while it stays
PENDING. The migration rejects exactly the PENDING rows of that action type; every other approval keeps its state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.migrations import MIGRATION_STATEMENTS, REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL
from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base
from app.services.approvals.registry import ApprovalRegistry

_NOW = datetime.now(UTC)

# (id, chat_id, action_type, status, expires_at)
_ROWS: list[tuple[str, str, str, str, datetime | None]] = [
    ("legacy-1", "chat-a", "tool_stuck", "PENDING", None),
    ("legacy-2", "chat-b", "tool_stuck", "PENDING", None),
    ("shell-3", "chat-a", "shell_command", "PENDING", _NOW + timedelta(minutes=5)),
    ("stuck-approved-4", "chat-a", "tool_stuck", "APPROVED", None),
    ("stuck-rejected-5", "chat-a", "tool_stuck", "REJECTED", None),
    ("lookalike-6", "chat-a", "tool_stuck_extra", "PENDING", None),
    ("lookalike-7", "chat-a", "Tool_Stuck", "PENDING", None),
]
_LEGACY_IDS = {"legacy-1", "legacy-2"}


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'approvals.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Base.metadata.tables["approvals"]]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        for record_id, chat_id, action_type, status, expires_at in _ROWS:
            db.add(
                ApprovalRecord(
                    id=record_id,
                    agent_id="default",
                    chat_id=chat_id,
                    thread_id="thread-1",
                    action_type=action_type,
                    status=status,
                    expires_at=expires_at,
                    resolved_at=None if status == "PENDING" else _NOW - timedelta(hours=1),
                    payload={},
                )
            )
        await db.commit()
    yield factory
    await engine.dispose()


async def _migrate(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as db:
        await db.execute(text(REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL))
        await db.commit()


async def _states(factory: async_sessionmaker[AsyncSession]) -> dict[str, tuple[str, datetime | None]]:
    async with factory() as db:
        records = (await db.execute(select(ApprovalRecord))).scalars().all()
        return {record.id: (record.status, record.resolved_at) for record in records}


def test_the_rejection_is_a_registered_migration() -> None:
    assert REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL in MIGRATION_STATEMENTS


@pytest.mark.asyncio
async def test_only_pending_tool_stuck_rows_are_rejected_and_a_replay_changes_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    before = await _states(session_factory)
    await _migrate(session_factory)
    after_first = await _states(session_factory)
    await _migrate(session_factory)
    after_replay = await _states(session_factory)

    for record_id, (status, resolved_at) in after_first.items():
        if record_id in _LEGACY_IDS:
            assert status == "REJECTED"
            assert resolved_at is not None
        else:
            assert (status, resolved_at) == before[record_id], record_id
    assert after_replay == after_first


@pytest.mark.asyncio
async def test_a_chat_held_by_a_legacy_row_is_free_after_the_migration_and_keeps_its_real_approval(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db:
            yield db

    with patch("app.services.approvals.registry.get_session", _session):
        # chat-a holds the legacy row, a shell approval and two look-alikes; chat-b holds only a legacy row
        assert await ApprovalRegistry.count_pending_for_chat("chat-a") == 4
        assert await ApprovalRegistry.count_pending_for_chat("chat-b") == 1

        await _migrate(session_factory)

        assert await ApprovalRegistry.count_pending_for_chat("chat-a") == 3
        assert await ApprovalRegistry.count_pending_for_chat("chat-b") == 0
