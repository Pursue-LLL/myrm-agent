"""Companion 测试共享 fixtures

为 companion 相关测试提供隔离的文件级 SQLite 数据库，
保证与其他模块的 autouse fixtures 不发生 session 冲突。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base


@pytest.fixture(autouse=True)
async def setup_companion_database(tmp_path: Path):
    """Create an isolated file-backed SQLite database for companion tests."""
    db_file = tmp_path / "test_companion.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def mock_get_session():
        async with TestSession() as session:
            try:
                yield session
            finally:
                await session.close()

    def mock_get_session_factory():
        return TestSession

    with (
        patch("app.database.connection.get_session", mock_get_session),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
        patch("app.platform_utils.get_session_factory", mock_get_session_factory),
    ):
        yield

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        pass
    finally:
        await engine.dispose()
