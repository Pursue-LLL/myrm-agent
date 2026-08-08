"""Shared SQLite test fixtures for the memory services test suite.

Keeps the persistent retry queue tests free of duplicated DB-bootstrap code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, MemoryExtractRetryModel

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def test_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SessionFactory]:
    """In-memory SQLite DB wired to app.database.connection.get_session."""
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

    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
            finally:
                await session.close()

    monkeypatch.setattr("app.database.connection.get_session", _session)
    monkeypatch.setattr(
        "app.database.repositories.uow.get_session_factory",
        lambda: factory,
    )
    yield factory
    await engine.dispose()


@pytest.fixture
def fetch_retry_row(
    test_db: SessionFactory,
) -> Callable[[str], Awaitable[MemoryExtractRetryModel | None]]:
    """Return a retry queue row by chat_id (None when absent)."""

    async def _fetch(chat_id: str) -> MemoryExtractRetryModel | None:
        async with test_db() as db:
            result = await db.execute(
                select(MemoryExtractRetryModel).where(
                    MemoryExtractRetryModel.chat_id == chat_id
                )
            )
            return result.scalar_one_or_none()

    return _fetch
