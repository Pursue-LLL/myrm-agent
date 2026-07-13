"""Tests for built-in agents initialization, update sync, and delete protection.

Tests:
1. initialize_builtin_agents creates all agents on first run
2. initialize_builtin_agents is idempotent (second run creates nothing)
3. initialize_builtin_agents updates spec-controlled fields on existing agents
4. Built-in agents cannot be deleted via AgentService
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Agent
from app.database.models.base import Base
from app.services.agent.builtin_initializer import (
    _BUILTIN_AGENTS,
    initialize_builtin_agents,
)
from app.services.agent.builtin_tool_ids import DEFAULT_ENABLED_BUILTIN_TOOLS


@pytest.fixture
async def test_db():
    """In-memory SQLite database for isolated testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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
        patch("app.services.agent.builtin_initializer.get_session", mock_get_session),
        patch(
            "app.database.repositories.uow.get_session_factory",
            mock_get_session_factory,
        ),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
    ):
        yield TestSession

    await engine.dispose()


@pytest.mark.asyncio
async def test_initialize_creates_all_builtin_agents(test_db: sessionmaker):
    """First call should create all built-in agents."""
    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.is_built_in.is_(True)))
        agents = result.scalars().all()

    assert len(agents) == len(_BUILTIN_AGENTS)

    agent_ids = {a.id for a in agents}
    for spec in _BUILTIN_AGENTS:
        assert spec.id in agent_ids

    for agent in agents:
        assert agent.is_built_in is True
        assert agent.is_public is True
        assert agent.name
        assert agent.description
        # search 模式智能体的提示词由 prompt_mode 提供，system_prompt 留空
        if agent.prompt_mode != "search":
            assert agent.system_prompt
        else:
            assert not agent.system_prompt
        assert agent.avatar and agent.avatar.startswith("icon:")
        assert agent.personality_style


@pytest.mark.asyncio
async def test_initialize_is_idempotent(test_db: sessionmaker):
    """Second call should not create duplicates."""
    await initialize_builtin_agents()
    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.is_built_in.is_(True)))
        agents = result.scalars().all()

    assert len(agents) == len(_BUILTIN_AGENTS)


@pytest.mark.asyncio
async def test_initialize_skips_existing_partial(test_db: sessionmaker):
    """If some agents already exist, only missing ones are created."""
    first_spec = _BUILTIN_AGENTS[0]
    async with test_db() as session:
        session.add(
            Agent(
                id=first_spec.id,
                name=first_spec.name,
                description=first_spec.description,
                avatar=f"icon:{first_spec.icon_id}",
                is_built_in=True,
                is_public=True,
                personality_style=first_spec.personality_style,
                system_prompt=first_spec.system_prompt,
                skill_ids=[],
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.is_built_in.is_(True)))
        agents = result.scalars().all()

    assert len(agents) == len(_BUILTIN_AGENTS)


@pytest.mark.asyncio
async def test_initialize_updates_outdated_spec_fields(test_db: sessionmaker):
    """If a built-in agent exists with outdated name/avatar/prompt, it gets synced."""
    first_spec = _BUILTIN_AGENTS[0]
    async with test_db() as session:
        session.add(
            Agent(
                id=first_spec.id,
                name="Old Name",
                description="Old description",
                avatar="emoji:❌",
                is_built_in=True,
                is_public=True,
                personality_style="humorous",
                system_prompt="Outdated prompt",
                skill_ids=["user-skill-1"],
                mcp_servers=["user-mcp"],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.id == first_spec.id))
        agent = result.scalar_one()

    assert agent.name == first_spec.name
    assert agent.description == first_spec.description
    assert agent.avatar == f"icon:{first_spec.icon_id}"
    assert agent.personality_style == first_spec.personality_style
    assert agent.system_prompt == first_spec.system_prompt
    # User-customizable fields must NOT be overwritten
    assert agent.skill_ids == ["user-skill-1"]
    assert agent.mcp_servers == ["user-mcp"]


@pytest.mark.asyncio
async def test_initialize_backfills_empty_skill_ids(test_db: sessionmaker):
    """Existing agents with empty skill_ids receive default prebuilt bindings."""
    dev_spec = next(s for s in _BUILTIN_AGENTS if s.id == "builtin-developer")
    assert dev_spec.default_skill_ids

    async with test_db() as session:
        session.add(
            Agent(
                id=dev_spec.id,
                name=dev_spec.name,
                description=dev_spec.description,
                is_built_in=True,
                is_public=True,
                personality_style=dev_spec.personality_style,
                system_prompt=dev_spec.system_prompt,
                skill_ids=[],
                skill_configs=None,
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.id == dev_spec.id))
        agent = result.scalar_one()

    assert agent.skill_ids == list(dev_spec.default_skill_ids)
    assert agent.skill_configs is not None
    for skill_id in dev_spec.default_skill_ids:
        assert agent.skill_configs[skill_id]["is_core"] is False


@pytest.mark.asyncio
async def test_initialize_no_update_when_already_synced(test_db: sessionmaker):
    """If all spec fields match, no update is performed (idempotent)."""
    await initialize_builtin_agents()

    # Capture state before second call
    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.is_built_in.is_(True)))
        {a.id: a.updated_at for a in result.scalars().all()}

    # Second call should not trigger updates
    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.is_built_in.is_(True)))
        agents = result.scalars().all()

    assert len(agents) == len(_BUILTIN_AGENTS)


@pytest.mark.asyncio
async def test_delete_builtin_agent_raises_permission_error(test_db: sessionmaker):
    """Deleting a built-in agent should raise PermissionError."""
    await initialize_builtin_agents()

    from app.services.agent.agent_service import AgentService

    with pytest.raises(PermissionError, match="cannot be deleted"):
        await AgentService.delete_agent(_BUILTIN_AGENTS[0].id)


@pytest.mark.asyncio
async def test_delete_regular_agent_succeeds(test_db: sessionmaker):
    """Deleting a non-built-in agent should work normally."""
    async with test_db() as session:
        session.add(
            Agent(
                id="user-agent-123",
                name="Test Agent",
                description="A test agent",
                is_built_in=False,
                skill_ids=[],
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    from app.services.agent.agent_service import AgentService

    success = await AgentService.delete_agent("user-agent-123")
    assert success is True


@pytest.mark.asyncio
async def test_update_cannot_remove_builtin_flag(test_db: sessionmaker):
    """Updating a built-in agent must not allow changing is_built_in to False."""
    await initialize_builtin_agents()

    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    agent_id = _BUILTIN_AGENTS[0].id

    result = await AgentService.update_agent(agent_id, AgentUpdate(is_built_in=False))
    assert result is not None
    assert result.profile.built_in is True


@pytest.mark.asyncio
async def test_update_regular_agent_can_set_builtin_flag(test_db: sessionmaker):
    """Non-built-in agents CAN have is_built_in changed (e.g., promoted to built-in)."""
    async with test_db() as session:
        session.add(
            Agent(
                id="regular-agent-1",
                name="Regular Agent",
                description="A regular agent",
                is_built_in=False,
                skill_ids=[],
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    result = await AgentService.update_agent("regular-agent-1", AgentUpdate(is_built_in=True))
    assert result is not None
    assert result.profile.built_in is True


@pytest.mark.asyncio
async def test_update_builtin_agent_other_fields_allowed(test_db: sessionmaker):
    """Built-in agents can still have their other fields updated (e.g., name, system_prompt)."""
    await initialize_builtin_agents()

    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    agent_id = _BUILTIN_AGENTS[0].id

    result = await AgentService.update_agent(
        agent_id,
        AgentUpdate(
            name="Custom General",
            description="User-customized general assistant",
            system_prompt="Custom prompt",
            skill_ids=["skill-1"],
            enabled_builtin_tools=["web_search"],
            max_iterations=50,
            personality_style="creative",
            subagent_ids=["sub-1"],
            mcp_ids=["mcp-1"],
            security_overrides={"sandbox": True},
            workspace_policy="INHERIT_REQUESTER",
        ),
    )
    assert result is not None
    assert result.profile.display_name == "Custom General"
    assert result.profile.description == "User-customized general assistant"
    assert result.profile.built_in is True
    assert result.profile.system_prompt == "Custom prompt"
    assert result.profile.max_iterations == 50


@pytest.mark.asyncio
async def test_update_nonexistent_agent_returns_none(test_db: sessionmaker):
    """Updating a non-existent agent should return None."""
    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    result = await AgentService.update_agent("nonexistent-id", AgentUpdate(name="Ghost"))
    assert result is None


@pytest.mark.asyncio
async def test_search_agents_have_correct_extended_fields(test_db: sessionmaker):
    """Search agents should have enabled_builtin_tools, engine_params, memory_policy, prompt_mode."""
    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.id.in_(["builtin-fast-search", "builtin-deep-search"])))
        agents = {a.id: a for a in result.scalars().all()}

    fast = agents["builtin-fast-search"]
    assert fast.enabled_builtin_tools == ["web_search"]
    assert fast.prompt_mode == "search"
    assert fast.engine_params == {"max_tool_calls": 8, "recursion_limit": 30}
    assert fast.memory_policy == {"write_policy": "conversation"}
    # 搜索提示词由 prompt_mode="search" 单一提供，system_prompt 留空避免重复注入
    assert not fast.system_prompt

    deep = agents["builtin-deep-search"]
    assert deep.enabled_builtin_tools == ["web_search", "answer_tool"]
    assert deep.prompt_mode == "search"
    assert deep.engine_params == {"max_tool_calls": 20, "recursion_limit": 50}
    assert deep.memory_policy == {"write_policy": "conversation"}
    assert not deep.system_prompt


@pytest.mark.asyncio
async def test_search_agents_update_syncs_extended_fields(test_db: sessionmaker):
    """If search agent extended fields drift, initializer syncs them back."""
    async with test_db() as session:
        session.add(
            Agent(
                id="builtin-fast-search",
                name="Quick Search",
                description="old desc",
                avatar="icon:search",
                is_built_in=True,
                is_public=True,
                personality_style="concise",
                system_prompt="old prompt",
                enabled_builtin_tools=["browser"],
                prompt_mode="full",
                engine_params={"max_tool_calls": 3},
                memory_policy=None,
                skill_ids=[],
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.id == "builtin-fast-search"))
        agent = result.scalar_one()

    assert agent.enabled_builtin_tools == ["web_search"]
    assert agent.prompt_mode == "search"
    assert agent.engine_params == {"max_tool_calls": 8, "recursion_limit": 30}
    assert agent.memory_policy == {"write_policy": "conversation"}
    # 旧的冗余 system_prompt 被同步清空，避免双重注入
    assert not agent.system_prompt


@pytest.mark.asyncio
async def test_initialize_syncs_hr_screener_tools_without_baseline(test_db: sessionmaker) -> None:
    """Stale file_ops in DB must be replaced with togglable-only list on startup sync."""
    async with test_db() as session:
        session.add(
            Agent(
                id="builtin-hr_screener",
                name="HR Resume Screener",
                description="old desc",
                avatar="icon:Briefcase",
                is_built_in=True,
                is_public=True,
                personality_style="professional",
                system_prompt="old prompt",
                enabled_builtin_tools=["web_search", "memory", "file_ops"],
                prompt_mode="full",
                skill_ids=[],
                mcp_servers=[],
                subagent_ids=[],
                model_config={},
            )
        )
        await session.commit()

    await initialize_builtin_agents()

    async with test_db() as session:
        result = await session.execute(select(Agent).where(Agent.id == "builtin-hr_screener"))
        agent = result.scalar_one()

    hr_spec = next(s for s in _BUILTIN_AGENTS if s.id == "builtin-hr_screener")
    assert agent.enabled_builtin_tools == list(hr_spec.enabled_builtin_tools)
