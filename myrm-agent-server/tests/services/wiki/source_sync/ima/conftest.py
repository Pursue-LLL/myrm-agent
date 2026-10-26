"""Fixtures for the ima connector suite: an isolated on-disk database.

A file database (not ``:memory:``) is deliberate: the importer runs concurrent workers with one short session each,
and an in-memory database would funnel them through a single shared connection whose rollbacks discard each other's
uncommitted work.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.services.wiki.source_sync.ima import importer

from .support import Downloads


@pytest_asyncio.fixture
async def ima_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ima.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


@pytest.fixture
def fast_importer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The importer paces its downloads for ima's rate limits; tests do not need to wait."""
    monkeypatch.setattr(importer, "_PACE_S", 0.0)


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> Downloads:
    fake = Downloads()
    monkeypatch.setattr("app.services.wiki.source_sync.ima.content.download_media", fake)
    return fake
