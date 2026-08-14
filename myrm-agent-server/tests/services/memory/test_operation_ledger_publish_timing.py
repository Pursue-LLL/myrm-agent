"""Publish timing contract for MemoryOperationLedgerService.record_event.

[POS]
回归保护：commit=True 时事件在落库后立即发布；commit=False 时发布延迟到
调用方事务成功提交（after_commit），回滚/不提交则完全不发布——杜绝 ghost event。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.database.models.memory import MemoryOperationEventModel
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

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


def _record_publish(
    published: list[MemoryOperationEventModel],
) -> Callable[[MemoryOperationEventModel], None]:
    def _append(row: MemoryOperationEventModel) -> None:
        published.append(row)

    return _append


async def test_commit_true_publishes_after_commit(db: AsyncSession) -> None:
    published: list[MemoryOperationEventModel] = []
    with patch(
        "app.services.memory.operation_ledger._publish_memory_operation_event",
        side_effect=_record_publish(published),
    ):
        row = await MemoryOperationLedgerService(db).record_event(
            kind=MemoryOperationKind.WRITE,
            status=MemoryOperationStatus.SUCCESS,
            summary="commit true path",
            target_kind="chat",
            target_id="chat-1",
            commit=True,
        )
    assert published == [row]


async def test_commit_false_publishes_after_outer_commit(db: AsyncSession) -> None:
    published: list[MemoryOperationEventModel] = []
    with patch(
        "app.services.memory.operation_ledger._publish_memory_operation_event",
        side_effect=_record_publish(published),
    ):
        row = await MemoryOperationLedgerService(db).record_event(
            kind=MemoryOperationKind.WRITE,
            status=MemoryOperationStatus.SUCCESS,
            summary="deferred publish",
            target_kind="chat",
            target_id="chat-2",
            commit=False,
        )
        assert published == []
        await db.commit()
    assert published == [row]


async def test_commit_false_not_published_on_rollback(db: AsyncSession) -> None:
    published: list[MemoryOperationEventModel] = []
    with patch(
        "app.services.memory.operation_ledger._publish_memory_operation_event",
        side_effect=_record_publish(published),
    ):
        await MemoryOperationLedgerService(db).record_event(
            kind=MemoryOperationKind.WRITE,
            status=MemoryOperationStatus.SUCCESS,
            summary="rollback discards publish",
            target_kind="chat",
            target_id="chat-3",
            commit=False,
        )
        assert published == []
        await db.rollback()
    assert published == []


async def test_commit_false_closed_without_commit_not_published(db: AsyncSession) -> None:
    published: list[MemoryOperationEventModel] = []
    with patch(
        "app.services.memory.operation_ledger._publish_memory_operation_event",
        side_effect=_record_publish(published),
    ):
        await MemoryOperationLedgerService(db).record_event(
            kind=MemoryOperationKind.WRITE,
            status=MemoryOperationStatus.SUCCESS,
            summary="never committed",
            target_kind="chat",
            target_id="chat-4",
            commit=False,
        )
    assert published == []


async def test_commit_false_batched_publishes_all_after_commit(db: AsyncSession) -> None:
    published: list[MemoryOperationEventModel] = []
    with patch(
        "app.services.memory.operation_ledger._publish_memory_operation_event",
        side_effect=_record_publish(published),
    ):
        ledger = MemoryOperationLedgerService(db)
        first = await ledger.record_event(
            kind=MemoryOperationKind.WRITE,
            status=MemoryOperationStatus.SUCCESS,
            summary="batch first",
            target_kind="chat",
            target_id="chat-5",
            commit=False,
        )
        second = await ledger.record_event(
            kind=MemoryOperationKind.FORGET,
            status=MemoryOperationStatus.SUCCESS,
            summary="batch second",
            target_kind="chat",
            target_id="chat-5",
            commit=False,
        )
        assert published == []
        await db.commit()
    assert published == [first, second]
