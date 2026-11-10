"""The built-in search agents run on the default memory policy; a row that still holds an override is cleared.

The migration touches exactly the two search ids. Every other agent, built-in or custom, keeps the policy it has.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.migrations import CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL, MIGRATION_STATEMENTS
from app.database.models import Agent
from app.database.models.base import Base

_OVERRIDE: dict[str, object] = {
    "read_scopes": ["global", "conversation"],
    "write_policy": "conversation",
    "allow_l3_extraction": False,
}
_CUSTOM_POLICY: dict[str, object] = {"write_policy": "task", "allow_l3_extraction": False}

_SEEDED: dict[str, dict[str, object]] = {
    "builtin-fast-search": _OVERRIDE,
    "builtin-deep-search": _OVERRIDE,
    "builtin-search-lookalike": _OVERRIDE,
    "builtin-general": _OVERRIDE,
    "custom-researcher": _CUSTOM_POLICY,
}
_CLEARED: dict[str, dict[str, object] | None] = {
    **_SEEDED,
    "builtin-fast-search": None,
    "builtin-deep-search": None,
}


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
                memory_policy=policy,
            )
            for agent_id, policy in _SEEDED.items()
        )
        await db.commit()
    yield factory
    await engine.dispose()


async def _clear(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as db:
        await db.execute(text(CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL))
        await db.commit()


async def _policies(factory: async_sessionmaker[AsyncSession]) -> dict[str, dict[str, object] | None]:
    async with factory() as db:
        agents = (await db.execute(select(Agent))).scalars().all()
        return {agent.id: agent.memory_policy for agent in agents}


def test_the_clearing_is_a_registered_migration() -> None:
    assert CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL in MIGRATION_STATEMENTS


@pytest.mark.asyncio
async def test_only_the_two_search_agents_lose_their_override(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _clear(session_factory)

    assert await _policies(session_factory) == _CLEARED


@pytest.mark.asyncio
async def test_clearing_again_changes_nothing(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _clear(session_factory)
    await _clear(session_factory)

    assert await _policies(session_factory) == _CLEARED
