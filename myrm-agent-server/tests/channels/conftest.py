"""Shared fixtures for the channel tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database.models.channel_message import ChannelMessageModel


@pytest.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async database session for isolated repository testing."""
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ChannelMessageModel.metadata.create_all(sync_conn, tables=[ChannelMessageModel.__table__])
        )

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()
