"""Notifications API tests — isolated in-memory DB (TestClient + async service share session)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base


@pytest.fixture(autouse=True)
async def notifications_isolated_db() -> Iterator[None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def mock_get_session():
        async with test_session() as session:
            try:
                yield session
            finally:
                await session.close()

    def mock_get_session_factory():
        return test_session

    with (
        patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
        patch("app.database.connection.get_session", mock_get_session),
        patch("app.services.infra.system_notification.get_session", mock_get_session),
        patch("app.platform_utils.get_session_factory", mock_get_session_factory),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
        patch("app.database.repositories.uow.get_session_factory", mock_get_session_factory),
    ):
        yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
