"""Tests for enabled_builtin_tools persist validation (AgentRepository)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from myrm_agent_harness.backends.profiles.types import AgentProfile
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.dto import AgentCreate
from app.database.migrations import ensure_raw_sql_schema
from app.database.models import Base
from app.database.repositories.agent_repo import AgentRepository
from app.services.agent.agent_service import AgentService
from app.services.agent.builtin_tool_ids import (
    InvalidBuiltinToolIdsError,
    persist_enabled_builtin_tools,
)


@pytest_asyncio.fixture
async def agent_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_raw_sql_schema(engine)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.database.repositories.uow as uow_module

    original_factory = uow_module.get_session_factory
    uow_module.get_session_factory = lambda: session_factory

    yield session_factory

    uow_module.get_session_factory = original_factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def test_persist_enabled_builtin_tools_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        persist_enabled_builtin_tools("web_search")


def test_persist_enabled_builtin_tools_defaults_when_none() -> None:
    from app.services.agent.builtin_tool_ids import DEFAULT_ENABLED_BUILTIN_TOOLS

    assert persist_enabled_builtin_tools(None) == list(DEFAULT_ENABLED_BUILTIN_TOOLS)


@pytest.mark.asyncio
async def test_repo_create_profile_persists_canonical_tools(agent_db) -> None:
    session_factory = agent_db
    async with session_factory() as session:
        profile = AgentProfile(
            id="agent-persist-create",
            display_name="Persist Create",
            metadata={"enabled_builtin_tools": ["file_ops", "code_execute", "web_search"]},
        )
        created = await AgentRepository.create_profile(session, profile)
        await session.commit()

    # AGENT_BASELINE_BUILTIN_TOOLS are stripped at persist; applied at runtime via apply_agent_baseline_tool_flags
    assert created.tools_allowed == ["web_search"]


@pytest.mark.asyncio
async def test_repo_update_tools_allowed_rejects_legacy(agent_db) -> None:
    created = await AgentService.create_agent(
        AgentCreate(name="Repo Tools Allowed", description="test")
    )
    agent_id = created.id
    session_factory = agent_db
    async with session_factory() as session:
        with pytest.raises(InvalidBuiltinToolIdsError):
            await AgentRepository.update_profile(
                session,
                agent_id,
                {"tools_allowed": ["web_search", "shell_exec"]},
            )


@pytest.mark.asyncio
async def test_repo_update_tools_allowed_persists_canonical(agent_db) -> None:
    created = await AgentService.create_agent(
        AgentCreate(name="Repo Tools Canonical", description="test")
    )
    agent_id = created.id
    session_factory = agent_db
    async with session_factory() as session:
        updated = await AgentRepository.update_profile(
            session,
            agent_id,
            {"tools_allowed": ["wiki", "planning", "web_search"]},
        )
        await session.commit()

    assert updated is not None
    assert updated.tools_allowed == ["wiki", "planning", "web_search"]


@pytest.mark.asyncio
async def test_repo_update_metadata_rejects_legacy_enabled_builtin_tools(agent_db) -> None:
    created = await AgentService.create_agent(
        AgentCreate(name="Repo Metadata Legacy", description="test")
    )
    agent_id = created.id
    session_factory = agent_db
    async with session_factory() as session:
        with pytest.raises(InvalidBuiltinToolIdsError):
            await AgentRepository.update_profile(
                session,
                agent_id,
                {"metadata": {"enabled_builtin_tools": ["code_interpreter"]}},
            )
