"""The prompt mode is system-managed (``full`` or ``search``); the two retired modes become ``full``.

The migration touches only rows holding ``lean`` or ``naked``. Every other row keeps its mode.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.migrations import MIGRATION_STATEMENTS, NORMALIZE_RETIRED_PROMPT_MODES_SQL
from app.database.models import Agent
from app.database.models.base import Base

_SEEDED: dict[str, str] = {
    "custom-lean": "lean",
    "custom-naked": "naked",
    "custom-full": "full",
    "builtin-fast-search": "search",
}
_NORMALIZED: dict[str, str] = {**_SEEDED, "custom-lean": "full", "custom-naked": "full"}


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agents.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Base.metadata.tables["agents"]]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all(
            Agent(
                id=agent_id,
                name=agent_id,
                description="",
                skill_ids=[],
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
                prompt_mode=mode,
            )
            for agent_id, mode in _SEEDED.items()
        )
        await db.commit()
    yield factory
    await engine.dispose()


async def _normalize(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as db:
        await db.execute(text(NORMALIZE_RETIRED_PROMPT_MODES_SQL))
        await db.commit()


async def _modes(factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with factory() as db:
        agents = (await db.execute(select(Agent))).scalars().all()
        return {agent.id: agent.prompt_mode for agent in agents}


def test_the_normalization_is_a_registered_migration() -> None:
    assert NORMALIZE_RETIRED_PROMPT_MODES_SQL in MIGRATION_STATEMENTS


@pytest.mark.asyncio
async def test_only_the_retired_modes_change(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _normalize(session_factory)

    assert await _modes(session_factory) == _NORMALIZED


@pytest.mark.asyncio
async def test_normalizing_again_changes_nothing(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _normalize(session_factory)
    await _normalize(session_factory)

    assert await _modes(session_factory) == _NORMALIZED
