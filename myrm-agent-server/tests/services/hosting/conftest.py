"""Shared fixtures for hosting service unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base


@pytest.fixture(autouse=True)
def passthrough_encryption():
    mock_service = MagicMock()
    mock_service.encrypt_if_needed = lambda _key, payload: (payload, False)
    mock_service.decrypt.return_value = "{}"
    with patch("app.services.hosting.targets.get_encryption_service", return_value=mock_service):
        with patch("app.services.hosting.credentials.get_encryption_service", return_value=mock_service):
            yield mock_service


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_hosting_unit?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
