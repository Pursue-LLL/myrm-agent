"""Shared Context memory-operation events must be persisted after API operations.

[POS]
回归保护：archive_shared_context / delete_shared_context_binding 的 ledger 事件此前只发布
SSE 而不落库（get_db_session 不自动 commit），刷新后事件消失。修复后必须落库。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.memory.operations.shared_context.shared_contexts import (
    archive_shared_context,
    delete_shared_context_binding,
)
from app.database.models import Base
from app.database.models.memory import MemoryOperationEventModel
from app.services.memory.shared_context.shared_context import SharedContextService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """In-memory SQLite session with full schema for one test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _fetch_events(
    db: AsyncSession,
    *,
    kind: str,
    target_kind: str,
) -> list[MemoryOperationEventModel]:
    result = await db.execute(
        select(MemoryOperationEventModel).where(
            MemoryOperationEventModel.source == "shared_context_api",
            MemoryOperationEventModel.kind == kind,
            MemoryOperationEventModel.target_kind == target_kind,
        )
    )
    return list(result.scalars().all())


async def test_archive_shared_context_persists_forget_event(db: AsyncSession) -> None:
    context = await SharedContextService(db).create_context(
        name="prod-ctx",
        description="events regression",
    )

    await archive_shared_context(context.id, db)

    rows = await _fetch_events(db, kind="forget", target_kind="shared_context")
    assert len(rows) == 1
    assert rows[0].target_id == context.id
    assert rows[0].memory_type == "shared_context"
    assert rows[0].metadata_json == {"name": "prod-ctx"}


async def test_delete_shared_context_binding_persists_write_event(db: AsyncSession) -> None:
    service = SharedContextService(db)
    context = await service.create_context(name="prod-ctx")
    binding = await service.bind_context(
        context_id=context.id,
        target_type="agent",
        target_id="agent-1",
    )
    assert binding is not None

    await delete_shared_context_binding(context.id, binding.id, db)

    rows = await _fetch_events(db, kind="write", target_kind="shared_context_binding")
    assert len(rows) == 1
    assert rows[0].target_id == binding.id
    assert rows[0].memory_id == context.id
