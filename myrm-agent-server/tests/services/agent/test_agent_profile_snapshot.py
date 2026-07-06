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
from app.database.models import Agent, AgentProfileSnapshot, Base
from app.database.repositories.agent_repo import AgentRepository
from app.services.agent.agent_service import AgentService
from app.services.agent.builtin_tool_ids import InvalidBuiltinToolIdsError
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


@pytest.mark.asyncio
async def test_repo_update_profile_rejects_legacy_enabled_builtin_tools(agent_db) -> None:
    agent_id = await _create_test_agent()
    session_factory = agent_db
    async with session_factory() as session:
        with pytest.raises(InvalidBuiltinToolIdsError):
            await AgentRepository.update_profile(
                session,
                agent_id,
                {"metadata": {"enabled_builtin_tools": ["web_search", "image_gen"]}},
            )


@pytest.mark.asyncio
async def test_rollback_rejects_legacy_enabled_builtin_tools_in_snapshot(agent_db) -> None:
    agent_id = await _create_test_agent()
    session_factory = agent_db
    async with session_factory() as session:
        session.add(
            AgentProfileSnapshot(
                id="snap-legacy-tools",
                agent_id=agent_id,
                snapshot_data={
                    "display_name": "Snapshot Test Agent",
                    "system_prompt": "You are a professional assistant.",
                    "skill_ids": [],
                    "enabled_builtin_tools": ["web_search", "image_gen"],
                },
                reason="legacy-tools",
            )
        )
        await session.commit()

    with pytest.raises(InvalidBuiltinToolIdsError):
        await ProfileSnapshotService.rollback_profile_to_snapshot(agent_id, "snap-legacy-tools")


@pytest.mark.asyncio
async def test_resolver_strips_legacy_enabled_builtin_tools_on_read(agent_db, monkeypatch) -> None:
    """Read path silently drops legacy IDs (write path still 422)."""
    import app.platform_utils as platform_utils

    monkeypatch.setattr(platform_utils, "get_session_factory", lambda: agent_db)

    agent_id = await _create_test_agent()
    session_factory = agent_db
    async with session_factory() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent_row = result.scalar_one()
        agent_row.enabled_builtin_tools = ["web_search", "image_gen"]
        await session.commit()

    resolver = get_agent_profile_resolver()
    resolver._cache.clear()  # noqa: SLF001

    resolved = await resolver.resolve(agent_id)
    assert resolved is not None
    assert resolved.enabled_builtin_tools == ("web_search",)


@pytest.mark.asyncio
async def test_rollback_restores_cron_post_run_verify_column(agent_db, monkeypatch) -> None:
    import app.platform_utils as platform_utils

    monkeypatch.setattr(platform_utils, "get_session_factory", lambda: agent_db)

    agent_id = await _create_test_agent()

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(cron_post_run_verify=True),
    )

    await AgentService.update_agent(
        agent_id,
        AgentUpdate(cron_post_run_verify=False, system_prompt="Mutated after verify toggle."),
    )

    resolver = get_agent_profile_resolver()
    resolver._cache.clear()  # noqa: SLF001
    before_rollback = await resolver.resolve(agent_id)
    assert before_rollback is not None
    assert before_rollback.cron_post_run_verify is False

    ok = await AgentService.rollback_profile(agent_id)
    assert ok is True

    resolver._cache.clear()  # noqa: SLF001
    after_rollback = await resolver.resolve(agent_id)
    assert after_rollback is not None
    assert after_rollback.cron_post_run_verify is True
    assert "professional assistant" in (after_rollback.system_prompt or "").lower()


@pytest.mark.asyncio
async def test_resolver_reads_canonical_enabled_builtin_tools(agent_db, monkeypatch) -> None:
    import app.platform_utils as platform_utils

    monkeypatch.setattr(platform_utils, "get_session_factory", lambda: agent_db)

    agent_id = await _create_test_agent()
    await AgentService.update_agent(
        agent_id,
        AgentUpdate(enabled_builtin_tools=["file_ops", "code_execute", "web_search"]),
    )

    resolver = get_agent_profile_resolver()
    resolver._cache.clear()  # noqa: SLF001
    resolved = await resolver.resolve(agent_id)
    assert resolved is not None
    assert resolved.enabled_builtin_tools == ("web_search",)
