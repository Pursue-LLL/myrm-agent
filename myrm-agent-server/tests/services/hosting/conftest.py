"""Shared fixtures for hosting service unit tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.services.config.encryption import ConfigEncryptionService


@pytest.fixture(autouse=True)
def real_encryption() -> Iterator[ConfigEncryptionService]:
    """The real sealing policy with a throwaway key, so tests read the same rows an instance stores."""
    service = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    with (
        patch("app.services.hosting.credentials.get_encryption_service", return_value=service),
        patch("app.services.config.migration.get_encryption_service", return_value=service),
    ):
        yield service


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_hosting_unit?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
