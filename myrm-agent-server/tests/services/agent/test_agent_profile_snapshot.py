"""Unit tests for Agent profile snapshot, WebUI diff snapshot, and rollback."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.dto import AgentCreate, AgentUpdate
from app.database.migrations import ensure_raw_sql_schema
from app.database.models import AgentProfileSnapshot, Base
from app.services.agent.agent_service import AgentService
from app.services.agent.profile_resolver import get_agent_profile_resolver
from app.services.agent.profile_snapshot_service import ProfileSnapshotService


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


async def _create_test_agent(name: str = "Snapshot Test Agent") -> str:
    profile = await AgentService.create_agent(
        AgentCreate(
            name=name,
            description="For snapshot tests",
            system_prompt="You are a professional assistant.",
            personality_style="professional",
            mcp_ids=["mcp-a"],
        )
    )
    return profile.id


@pytest.mark.asyncio
async def test_webui_update_creates_snapshot_and_rollback_works(agent_db) -> None:
    agent_id = await _create_test_agent()

    outcome = await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="You are a cool hacker."),
    )
    assert outcome is not None
    assert outcome.snapshot_saved is True

    session_factory = agent_db
    async with session_factory() as session:
        result = await session.execute(select(AgentProfileSnapshot).where(AgentProfileSnapshot.agent_id == agent_id))
        assert len(result.scalars().all()) >= 1

    ok = await AgentService.rollback_profile(agent_id)
    assert ok is True

    agent = await AgentService.get_agent_by_id(agent_id)
    assert agent is not None
    assert "professional assistant" in (agent.system_prompt or "").lower()


@pytest.mark.asyncio
async def test_avatar_only_update_does_not_create_snapshot(agent_db) -> None:
    agent_id = await _create_test_agent()

    outcome = await AgentService.update_agent(
        agent_id,
        AgentUpdate(avatar_url="gradient:2"),
    )
    assert outcome is not None
    assert outcome.snapshot_saved is True

    count = await AgentService.count_profile_snapshots(agent_id)
    assert count == 0


@pytest.mark.asyncio
async def test_rollback_fails_without_snapshot(agent_db) -> None:
    agent_id = await _create_test_agent()
    assert await AgentService.rollback_profile(agent_id) is False


@pytest.mark.asyncio
async def test_snapshot_retention_keeps_latest_ten(agent_db) -> None:
    agent_id = await _create_test_agent()

    for i in range(12):
        await AgentService.save_profile_snapshot(agent_id, reason=f"snap-{i}")

    session_factory = agent_db
    async with session_factory() as session:
        result = await session.execute(select(AgentProfileSnapshot).where(AgentProfileSnapshot.agent_id == agent_id))
        snapshots = result.scalars().all()
        assert len(snapshots) <= 10


@pytest.mark.asyncio
async def test_list_profile_snapshots(agent_db) -> None:
    agent_id = await _create_test_agent()
    await AgentService.save_profile_snapshot(agent_id, reason="first")
    await AgentService.save_profile_snapshot(agent_id, reason="second")

    snapshots = await AgentService.list_profile_snapshots(agent_id)
    assert len(snapshots) == 2
    reasons = {snapshot.reason for snapshot in snapshots}
    assert reasons == {"first", "second"}


@pytest.mark.asyncio
async def test_rollback_to_specific_snapshot(agent_db) -> None:
    agent_id = await _create_test_agent()

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="First mutation."),
    )
    snapshots = await AgentService.list_profile_snapshots(agent_id)
    assert len(snapshots) >= 1
    target_id = snapshots[-1].id

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="Second mutation."),
    )

    ok = await AgentService.rollback_profile_to_snapshot(agent_id, target_id)
    assert ok is True

    agent = await AgentService.get_agent_by_id(agent_id)
    assert agent is not None
    assert "professional assistant" in (agent.system_prompt or "").lower()


@pytest.mark.asyncio
async def test_time_machine_restore_keeps_pre_rollback_snapshot(agent_db) -> None:
    agent_id = await _create_test_agent()

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="First mutation."),
    )
    snapshots = await AgentService.list_profile_snapshots(agent_id)
    assert len(snapshots) >= 1
    target_id = snapshots[-1].id

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="Second mutation."),
    )

    ok = await ProfileSnapshotService.rollback_profile_to_snapshot(agent_id, target_id)
    assert ok is True

    remaining = await AgentService.list_profile_snapshots(agent_id)
    pre_rollbacks = [s for s in remaining if s.reason == "pre-rollback"]
    assert len(pre_rollbacks) == 1
    assert pre_rollbacks[0].snapshot_data.get("system_prompt") == "Second mutation."


@pytest.mark.asyncio
async def test_webui_update_visible_via_profile_resolver(agent_db, monkeypatch) -> None:
    import app.platform_utils as platform_utils

    monkeypatch.setattr(platform_utils, "get_session_factory", lambda: agent_db)

    agent_id = await _create_test_agent()

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="Channel-visible prompt text."),
    )

    resolver = get_agent_profile_resolver()
    resolved = await resolver.resolve(agent_id)
    assert resolved is not None
    assert "Channel-visible prompt text." in (resolved.system_prompt or "")


@pytest.mark.asyncio
async def test_rollback_invalidates_resolver_cache(agent_db, monkeypatch) -> None:
    import app.platform_utils as platform_utils

    monkeypatch.setattr(platform_utils, "get_session_factory", lambda: agent_db)

    agent_id = await _create_test_agent()
    resolver = get_agent_profile_resolver()
    resolver._cache.clear()  # noqa: SLF001

    before = await resolver.resolve(agent_id)
    assert before is not None
    assert "professional" in (before.system_prompt or "").lower()

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(system_prompt="Mutated resolver prompt."),
    )

    after_update = await resolver.resolve(agent_id)
    assert after_update is not None
    assert "mutated resolver" in (after_update.system_prompt or "").lower()

    await AgentService.rollback_profile(agent_id)

    after_rollback = await resolver.resolve(agent_id)
    assert after_rollback is not None
    assert "professional" in (after_rollback.system_prompt or "").lower()


@pytest.mark.asyncio
async def test_rollback_preserves_mcp_ids(agent_db) -> None:
    agent_id = await _create_test_agent()

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(mcp_ids=["mcp-b"]),
    )
    await AgentService.rollback_profile(agent_id)

    agent = await AgentService.get_agent_by_id(agent_id)
    assert agent is not None
    metadata = agent.metadata or {}
    assert metadata.get("mcp_ids") == ["mcp-a"]
