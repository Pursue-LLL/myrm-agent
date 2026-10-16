"""Shared fixtures for the curator tests that read agent profiles and cron jobs from a real database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.skills.curator import bound_skills as bound_skills_module
from app.database.models import Base


@pytest.fixture
async def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    """Isolated SQLite DB that ``bound_skill_names`` reads through its own ``get_session``."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bound.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def isolated_session() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            yield db

    monkeypatch.setattr(bound_skills_module, "get_session", isolated_session)
    async with factory() as seed:
        yield seed
    await engine.dispose()
