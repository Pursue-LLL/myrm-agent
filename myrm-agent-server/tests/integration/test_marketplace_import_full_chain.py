"""Real full-chain integration tests: marketplace import + allow_discovery.

These tests exercise the actual production code paths against a real
in-memory SQLite database and real skill filesystem writes — no mocks on the
critical paths:

1. ``import_agent_package``: contract validation -> skill write -> subagent
   creation -> ID remap -> agent creation, all persisted in a real DB.
2. ``/api/admin/import-agent-profile`` endpoint: force install and force-push
   update (including pre-push snapshot persistence and event bus emission).
3. ``team_protocol._resolve_roster`` dynamic discovery honoring
   ``allow_discovery``.

They run entirely in-process (ASGI) and require no live server, LLM, or Chrome.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai_agents.team_protocol import _resolve_roster
from app.api.internal.import_agent_profile import router as import_agent_profile_router
from app.core.memory.adapters.policy import MemoryWritePolicy
from app.core.skills.creation.service import SkillCreationService
from app.database.dto import AgentCreate
from app.database.migrations import ensure_raw_sql_schema
from app.database.models import Agent, AgentProfileSnapshot, Base
from app.services.agent.agent_service import AgentService
from app.services.agent.marketplace import (
    build_marketplace_package,
    import_agent_package,
)
from app.services.event.app_event_bus import AppEventType, get_event_bus

_PUBLISHER_SKILL_ID = "publisher-skill-id"
_PUBLISHER_SUB_ID = "publisher-sub-id"
_PUBLISHER_ENTRY_ID = "entry-chain"


@pytest.fixture(autouse=True)
def _init_skill_state_manager(tmp_path: Path) -> Iterator[None]:
    """Mirror app startup: initialize the global SkillStateManager singleton.

    ``create_agent`` validates ``skill_configs`` through the state manager;
    without startup initialization every import fails with RuntimeError.
    """
    import app.core.skills.state_manager_instance as smi

    previous = smi._state_manager
    smi.init_state_manager(base_dir=str(tmp_path / "skill-state"))
    yield
    smi._state_manager = previous


@pytest_asyncio.fixture
async def agent_db():
    """Real in-memory SQLite with full schema, wired into every UnitOfWork."""
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


@pytest.fixture
def skill_store(tmp_path: Path) -> SkillCreationService:
    """Real SkillCreationService writing into an isolated temp directory."""
    return SkillCreationService(base_path=tmp_path / "skills")


def _build_package(
    *,
    agent_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a contract-compliant marketplace package with bundled skill+subagent."""
    return build_marketplace_package(
        agent_profile=agent_profile
        or {
            "display_name": "Publisher Agent",
            "description": "published desc",
            "system_prompt": "You are a published agent.",
            "skill_ids": [_PUBLISHER_SKILL_ID],
            "skill_configs": {_PUBLISHER_SKILL_ID: {"enabled": True}},
            "subagent_ids": [_PUBLISHER_SUB_ID],
            "enabled_builtin_tools": [],
        },
        bundled_skills=[
            {
                "id": _PUBLISHER_SKILL_ID,
                "name": "pub-skill",
                "content": ("---\nname: pub-skill\ndescription: test skill\n---\n# Pub Skill\n\nDo things."),
                "description": "test skill",
                "resources": {"scripts/run.py": "print('hi')"},
            },
        ],
        bundled_mcp_configs=[],
        bundled_subagents=[
            {
                "original_id": _PUBLISHER_SUB_ID,
                "profile": {
                    "display_name": "Publisher Sub",
                    "description": "helper subagent",
                    "system_prompt": "You are a helper.",
                    "enabled_builtin_tools": [],
                },
            },
        ],
    )


def _import_app() -> FastAPI:
    app = FastAPI()
    app.include_router(import_agent_profile_router)
    return app


# ---------------------------------------------------------------------------
# 1. import_agent_package real full chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_agent_package_full_chain(agent_db, skill_store: SkillCreationService) -> None:
    """Real import: contract gate, skill write, subagent create, ID remap, binding."""
    package = _build_package()

    agent_id = await import_agent_package(
        skill_store,
        package,
        marketplace_entry_id=_PUBLISHER_ENTRY_ID,
    )

    assert agent_id

    # Skill landed on the real filesystem.
    skill_file = skill_store.base_path / "pub-skill" / "SKILL.md"
    assert skill_file.is_file()
    assert "Do things." in skill_file.read_text(encoding="utf-8")

    profile = await AgentService.get_agent_by_id(agent_id)
    assert profile is not None
    assert profile.display_name == "Publisher Agent"
    assert profile.description == "published desc"

    # Publisher skill ID was remapped to the local skill ID.
    assert len(profile.skills) == 1
    assert profile.skills[0] != _PUBLISHER_SKILL_ID
    local_skill_dir = skill_store.base_path / "pub-skill"
    from app.core.skills.providers.local import compute_local_skill_id

    assert profile.skills[0] == compute_local_skill_id(local_skill_dir)

    # Subagent was created and its ID remapped into the roster.
    subagent_ids = (profile.metadata or {}).get("subagent_ids")
    assert isinstance(subagent_ids, list)
    assert len(subagent_ids) == 1
    assert subagent_ids[0] != _PUBLISHER_SUB_ID
    subagent = await AgentService.get_agent_by_id(subagent_ids[0])
    assert subagent is not None
    assert subagent.display_name == "Publisher Sub"

    # Marketplace entry binding was persisted in engine_params.
    engine_params = (profile.metadata or {}).get("engine_params")
    assert isinstance(engine_params, dict)
    assert engine_params.get("marketplace_entry_id") == _PUBLISHER_ENTRY_ID

    # Imported agent is discoverable by default.
    assert (profile.metadata or {}).get("allow_discovery") is not False


@pytest.mark.asyncio
async def test_import_agent_package_rolls_back_atomically(agent_db, skill_store: SkillCreationService) -> None:
    """A failing subagent profile must roll back agent + skills atomically."""
    package = build_marketplace_package(
        agent_profile={
            "display_name": "Rollback Agent",
            "description": "desc",
            "system_prompt": "sys",
            "skill_ids": [_PUBLISHER_SKILL_ID],
            "subagent_ids": [],
            "enabled_builtin_tools": [],
        },
        bundled_skills=[
            {
                "id": _PUBLISHER_SKILL_ID,
                "name": "rollback-skill",
                "content": ("---\nname: rollback-skill\ndescription: test\n---\n# Rollback Skill"),
                "description": "test",
                "resources": {},
            },
        ],
        bundled_mcp_configs=[],
        bundled_subagents=[],
    )
    # The second bundle carries an invalid subagent memory_policy that fails
    # AgentCreate.model_validate during subagent creation (after the skill was
    # already written) — forcing the atomic rollback path.
    invalid_package = build_marketplace_package(
        agent_profile={
            "display_name": "Rollback Agent 2",
            "description": "desc",
            "system_prompt": "sys",
            "skill_ids": [_PUBLISHER_SKILL_ID],
            "subagent_ids": ["broken-sub"],
            "enabled_builtin_tools": [],
        },
        bundled_skills=[
            {
                "id": _PUBLISHER_SKILL_ID,
                "name": "rollback-skill-2",
                "content": ("---\nname: rollback-skill-2\ndescription: test\n---\n# Rollback Skill 2"),
                "description": "test",
                "resources": {},
            },
        ],
        bundled_mcp_configs=[],
        bundled_subagents=[
            {
                "original_id": "broken-sub",
                "profile": {
                    "display_name": "Broken Sub",
                    "description": "broken",
                    "system_prompt": "sys",
                    "memory_policy": {"write_policy": "not-a-valid-policy"},
                },
            },
        ],
    )

    # Sanity: the first import succeeds.
    await import_agent_package(skill_store, package)
    skill_file = skill_store.base_path / "rollback-skill" / "SKILL.md"
    assert skill_file.is_file()

    # The second import fails during subagent creation and must roll back the
    # main agent + the skill it already wrote.
    with pytest.raises(ValueError):
        await import_agent_package(skill_store, invalid_package)

    profiles = await AgentService.get_agent_list(page=1, page_size=50)
    names = {p.display_name for p in profiles[0]}
    assert "Rollback Agent 2" not in names
    assert "Rollback Agent" in names
    assert not (skill_store.base_path / "rollback-skill-2").exists()


# ---------------------------------------------------------------------------
# 2. import-agent-profile endpoint real HTTP chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_endpoint_installs_through_http(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST import-agent-profile (force=False) installs against a real DB."""
    monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
    transport = ASGITransport(app=_import_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": False,
                "marketplace_entry_id": "entry-http",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "installed"
    assert data["agent_id"]

    profile = await AgentService.get_agent_by_id(data["agent_id"])
    assert profile is not None
    assert profile.display_name == "Publisher Agent"
    assert (skill_store.base_path / "pub-skill" / "SKILL.md").is_file()

    # The exact same package is rejected on re-install (skill name conflict).
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": False,
                "marketplace_entry_id": "entry-http-2",
            },
        )
    assert resp.status_code == 400
    assert "bundled skills already exist locally" in resp.text


@pytest.mark.asyncio
async def test_force_push_preserves_skill_bindings_with_real_db(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push keeps local skill bindings and applies config updates."""
    monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
    transport = ASGITransport(app=_import_app())
    bus = get_event_bus()
    queue = bus.subscribe()

    try:
        # 1) Real install.
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/import-agent-profile",
                json={
                    "package": _build_package(),
                    "force": False,
                    "marketplace_entry_id": "entry-fp",
                },
            )
        assert resp.status_code == 200
        agent_id = resp.json()["agent_id"]

        profile = await AgentService.get_agent_by_id(agent_id)
        assert profile is not None
        original_skill_id = profile.skills[0]
        original_subagent_ids = (profile.metadata or {}).get("subagent_ids")

        # 2) Force-push a newer publisher package referencing a *different*
        #    publisher skill/subagent ID. Bindings must stay local.
        force_package = build_marketplace_package(
            agent_profile={
                "display_name": "Publisher Agent v2",
                "description": "v2 desc",
                "system_prompt": "New prompt.",
                "model": "gpt-4.1",
                "memory_policy": {"write_policy": "inherit"},
                "workspace_policy": "ISOLATED_COPY",
                "cron_post_run_verify": True,
                "command_bindings": [
                    {
                        "command_name": "daily-report",
                        "skill_ids": [],
                        "description": "daily report",
                    }
                ],
                "skill_ids": ["publisher-skill-v2"],
                "skill_configs": {"publisher-skill-v2": {"enabled": True}},
                "subagent_ids": ["publisher-sub-v2"],
                "enabled_builtin_tools": ["web_search"],
                "allow_discovery": False,
            },
            bundled_skills=[],
            bundled_mcp_configs=[],
            bundled_subagents=[],
        )
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/import-agent-profile",
                json={
                    "package": force_package,
                    "force": True,
                    "marketplace_entry_id": "entry-fp",
                },
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "force_updated"
        assert data["snapshot_id"]

        # Bindings preserved, config updated.
        updated = await AgentService.get_agent_by_id(agent_id)
        assert updated is not None
        assert updated.skills == [original_skill_id]
        assert (updated.metadata or {}).get("subagent_ids") == original_subagent_ids
        assert updated.display_name == "Publisher Agent v2"
        assert updated.system_prompt == "New prompt."
        assert updated.model == "gpt-4.1"
        assert (updated.metadata or {}).get("allow_discovery") is False
        assert updated.tools_allowed == ["web_search"]

        # Non-skill config fields landed on the real DB.
        assert (updated.metadata or {}).get("workspace_policy") == "ISOLATED_COPY"
        assert (updated.metadata or {}).get("cron_post_run_verify") is True
        assert updated.command_bindings is not None
        assert updated.command_bindings[0].command_name == "daily-report"
        assert updated.memory_policy is not None
        assert updated.memory_policy.write_policy == MemoryWritePolicy.INHERIT

        # Pre-force-push snapshot persisted in the real DB.
        async with agent_db() as session:
            snapshots = (
                (await session.execute(select(AgentProfileSnapshot).where(AgentProfileSnapshot.agent_id == agent_id)))
                .scalars()
                .all()
            )
        assert len(snapshots) >= 1
        assert any(s.reason == "pre-force-push" for s in snapshots)

        # AGENT_CONFIG_UPDATED event emitted on the real in-process bus.
        events: list[object] = []
        while not queue.empty():
            events.append(queue.get_nowait())
        assert any(getattr(e, "event_type", None) == AppEventType.AGENT_CONFIG_UPDATED for e in events)
    finally:
        bus.unsubscribe(queue)


@pytest.mark.asyncio
async def test_force_push_unresolved_binding_fails_closed_real_db(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push with an unknown marketplace entry returns 404 before any write."""
    monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
    transport = ASGITransport(app=_import_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
                "marketplace_entry_id": "entry-not-installed",
            },
        )

    assert resp.status_code == 404
    assert "marketplace_entry_id" in resp.text

    async with agent_db() as session:
        agents = (await session.execute(select(Agent))).scalars().all()
    assert agents == []


# ---------------------------------------------------------------------------
# 3. allow_discovery dynamic-roster full chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_discovery_filters_allow_discovery_real_db(agent_db) -> None:
    """Only discoverable agents appear in the dynamic roster."""
    leader = await AgentService.create_agent(
        AgentCreate(
            name="Leader",
            description="team leader",
            system_prompt="sys",
            allow_discovery=True,
        )
    )
    visible = await AgentService.create_agent(
        AgentCreate(
            name="Visible Helper",
            description="can be discovered",
            system_prompt="sys",
            allow_discovery=True,
        )
    )
    hidden = await AgentService.create_agent(
        AgentCreate(
            name="Hidden Helper",
            description="opts out of discovery",
            system_prompt="sys",
            allow_discovery=False,
        )
    )

    roster = await _resolve_roster([], leader_id=leader.id, dynamic_discovery=True)
    roster_ids = {entry.agent_id for entry in roster}

    assert visible.id in roster_ids
    assert hidden.id not in roster_ids
    assert leader.id not in roster_ids


@pytest.mark.asyncio
async def test_discovery_defaults_on_when_not_set(agent_db) -> None:
    """Agents created without an explicit flag are discoverable by default."""
    profile = await AgentService.create_agent(
        AgentCreate(
            name="Default Helper",
            description="no explicit flag",
            system_prompt="sys",
        )
    )
    assert (profile.metadata or {}).get("allow_discovery") is True

    roster = await _resolve_roster([], dynamic_discovery=True)
    roster_ids = {entry.agent_id for entry in roster}
    assert profile.id in roster_ids


# ---------------------------------------------------------------------------
# 4. Real user flows: install -> update -> rollback, discovery toggling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allow_discovery_update_flow_real_db(agent_db) -> None:
    """Toggling allow_discovery via update_agent changes roster membership."""
    from app.database.dto import AgentUpdate as AgentUpdateDTO

    profile = await AgentService.create_agent(
        AgentCreate(
            name="Toggle Helper",
            description="helper",
            system_prompt="sys",
            allow_discovery=True,
        )
    )
    roster = await _resolve_roster([], dynamic_discovery=True)
    assert profile.id in {entry.agent_id for entry in roster}

    # The user flips the switch off — dynamic discovery must drop it.
    await AgentService.update_agent(
        profile.id,
        AgentUpdateDTO(
            name="Toggle Helper",
            description="helper",
            system_prompt="sys",
            allow_discovery=False,
        ),
    )
    updated = await AgentService.get_agent_by_id(profile.id)
    assert updated is not None
    assert (updated.metadata or {}).get("allow_discovery") is False

    roster = await _resolve_roster([], dynamic_discovery=True)
    assert profile.id not in {entry.agent_id for entry in roster}

    # Flipping it back on restores roster membership.
    await AgentService.update_agent(
        profile.id,
        AgentUpdateDTO(
            name="Toggle Helper",
            description="helper",
            system_prompt="sys",
            allow_discovery=True,
        ),
    )
    roster = await _resolve_roster([], dynamic_discovery=True)
    assert profile.id in {entry.agent_id for entry in roster}


@pytest.mark.asyncio
async def test_imported_agent_joins_dynamic_roster(agent_db, skill_store: SkillCreationService) -> None:
    """A marketplace-imported agent is discoverable by default in the roster."""
    agent_id = await import_agent_package(
        skill_store,
        _build_package(),
        marketplace_entry_id="entry-roster",
    )
    profile = await AgentService.get_agent_by_id(agent_id)
    assert profile is not None
    assert (profile.metadata or {}).get("allow_discovery") is not False

    roster = await _resolve_roster([], dynamic_discovery=True)
    assert agent_id in {entry.agent_id for entry in roster}


@pytest.mark.asyncio
async def test_rollback_restores_pre_force_push_config_real_db(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push then rollback restores the pre-push configuration."""
    monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
    transport = ASGITransport(app=_import_app())

    # 1) Install v1.
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(
                    agent_profile={
                        "display_name": "Publisher Agent",
                        "description": "v1 desc",
                        "system_prompt": "v1 prompt",
                        "skill_ids": [_PUBLISHER_SKILL_ID],
                        "skill_configs": {_PUBLISHER_SKILL_ID: {"enabled": True}},
                        "subagent_ids": [],
                        "enabled_builtin_tools": [],
                    }
                ),
                "force": False,
                "marketplace_entry_id": "entry-rollback",
            },
        )
    assert resp.status_code == 200
    agent_id = resp.json()["agent_id"]

    # 2) Force-push v2 (config changed).
    force_package = build_marketplace_package(
        agent_profile={
            "display_name": "Publisher Agent v2",
            "description": "v2 desc",
            "system_prompt": "v2 prompt",
            "model": "gpt-4.1",
            "skill_ids": [],
            "subagent_ids": [],
            "enabled_builtin_tools": [],
        },
        bundled_skills=[],
        bundled_mcp_configs=[],
        bundled_subagents=[],
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": force_package,
                "force": True,
                "marketplace_entry_id": "entry-rollback",
            },
        )
    assert resp.status_code == 200, resp.text
    updated = await AgentService.get_agent_by_id(agent_id)
    assert updated is not None
    assert updated.display_name == "Publisher Agent v2"

    # 3) Rollback to the pre-force-push snapshot.
    from app.services.agent.profile.profile_snapshot_service import (
        ProfileSnapshotService,
    )

    rolled_back = await ProfileSnapshotService.rollback_profile(agent_id)
    assert rolled_back is True

    restored = await AgentService.get_agent_by_id(agent_id)
    assert restored is not None
    assert restored.display_name == "Publisher Agent"
    assert restored.system_prompt == "v1 prompt"
    assert restored.skills == updated.skills


@pytest.mark.asyncio
async def test_force_push_via_target_agent_id_real_db(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push can target an explicit agent_id without an entry binding."""
    monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
    transport = ASGITransport(app=_import_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": False,
                "marketplace_entry_id": "entry-target-id",
            },
        )
    assert resp.status_code == 200
    agent_id = resp.json()["agent_id"]

    # 2) Force-push via target_agent_id (no marketplace_entry_id).
    force_package = build_marketplace_package(
        agent_profile={
            "display_name": "Renamed via target",
            "description": "target desc",
            "system_prompt": "target prompt",
            "skill_ids": [],
            "subagent_ids": [],
            "enabled_builtin_tools": [],
        },
        bundled_skills=[],
        bundled_mcp_configs=[],
        bundled_subagents=[],
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": force_package,
                "force": True,
                "target_agent_id": agent_id,
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "force_updated"

    updated = await AgentService.get_agent_by_id(agent_id)
    assert updated is not None
    assert updated.display_name == "Renamed via target"


@pytest.mark.asyncio
async def test_force_push_unknown_target_agent_returns_404(agent_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force-push with a non-existent target_agent_id fails closed."""
    transport = ASGITransport(app=_import_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
                "target_agent_id": "no-such-agent",
            },
        )
    assert resp.status_code == 404

    async with agent_db() as session:
        agents = (await session.execute(select(Agent))).scalars().all()
    assert agents == []


@pytest.mark.asyncio
async def test_sandbox_rejects_bundled_skills_real_db(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In sandbox deployment, bundled-skill imports fail closed end-to-end."""
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()

    try:
        monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
        transport = ASGITransport(app=_import_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/import-agent-profile",
                json={
                    "package": _build_package(),
                    "force": False,
                    "marketplace_entry_id": "entry-sandbox",
                },
            )
        assert resp.status_code == 400
        assert "bundled skills are not supported in sandbox" in resp.text

        # No skill was written, no agent was created.
        assert not (skill_store.base_path / "pub-skill").exists()
        async with agent_db() as session:
            agents = (await session.execute(select(Agent))).scalars().all()
        assert agents == []
    finally:
        monkeypatch.delenv("DEPLOY_MODE", raising=False)
        get_deploy_mode.cache_clear()
        _reset_capabilities_cache_for_testing()


@pytest.mark.asyncio
async def test_cp_token_rejected_when_configured(
    agent_db,
    skill_store: SkillCreationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a CP token is configured, missing/mismatched headers are rejected."""
    from pydantic import SecretStr

    from app.config.settings import settings

    monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr("cp-secret"))
    monkeypatch.setattr("app.core.skills.creation.service.skill_creation_service", skill_store)
    transport = ASGITransport(app=_import_app())

    # Missing header -> 401.
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={"package": _build_package(), "force": False},
        )
    assert resp.status_code == 401

    # Wrong token -> 401.
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={"package": _build_package(), "force": False},
            headers={"X-Telemetry-Token": "wrong"},
        )
    assert resp.status_code == 401

    # Correct token -> passes the gate (installs).
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={"package": _build_package(), "force": False},
            headers={"X-Telemetry-Token": "cp-secret"},
        )
    assert resp.status_code == 200
