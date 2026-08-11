"""Unit tests for the CP→sandbox Agent profile import endpoint.

Covers:
- Force-push keeps locally established skill bindings (publisher-side skill_ids
  are not blindly copied into the sandbox Agent)
- Force-push keeps locally established subagent bindings (publisher-side
  subagent_ids are not blindly copied either)
- Force-push still applies config updates (display name, prompt, model, etc.)
- Pre-force-push snapshot + config-updated event are emitted
- Force-push fails closed when the target Agent/binding is missing
- Sandbox deployment rejects bundled-skill imports at the endpoint (HTTP 400)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.internal.import_agent_profile import router as import_agent_profile_router


class FakeExistingAgent:
    def __init__(self, agent_id: str) -> None:
        self.id = agent_id


class FakeAgentRepo:
    def __init__(self) -> None:
        self.updated: dict[str, object] | None = None
        self.updated_agent_id: str | None = None
        self.committed = False

    async def update_profile(self, agent_id: str, updates: dict[str, object]) -> None:
        self.updated = updates
        self.updated_agent_id = agent_id


class FakeUnitOfWork:
    def __init__(self, repo: FakeAgentRepo) -> None:
        self.agent_repo = repo

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def commit(self) -> None:
        self.agent_repo.committed = True


def _build_package(
    *,
    agent_profile: dict[str, object] | None = None,
    bundled_skills: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    from app.services.agent.marketplace import build_marketplace_package

    return build_marketplace_package(
        agent_profile=agent_profile
        or {
            "display_name": "Publisher Agent",
            "description": "published desc",
            "system_prompt": "You are a published agent.",
            "skill_ids": ["publisher-skill-id"],
            "skill_configs": {"publisher-skill-id": {"enabled": True}},
            "subagent_ids": [],
            "enabled_builtin_tools": [],
        },
        bundled_skills=bundled_skills or [],
        bundled_mcp_configs=[],
        bundled_subagents=[],
    )


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(import_agent_profile_router)
    return app


@pytest.fixture
def fake_repo() -> FakeAgentRepo:
    return FakeAgentRepo()


def _patch_force_push_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    fake_repo: FakeAgentRepo,
    *,
    existing: FakeExistingAgent | None = None,
) -> tuple[AsyncMock, AsyncMock, MagicMock]:
    """Patch AgentService/ProfileSnapshotService/UnitOfWork/event bus for force-push."""
    get_agent = AsyncMock(return_value=existing)
    save_snapshot = AsyncMock(return_value="snapshot-1")
    fake_bus = MagicMock()

    monkeypatch.setattr(
        "app.services.agent.agent_service.AgentService.get_agent_by_id",
        get_agent,
    )
    monkeypatch.setattr(
        "app.services.agent.profile.profile_snapshot_service.ProfileSnapshotService.save_profile_snapshot",
        save_snapshot,
    )
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile.UnitOfWork",
        lambda: FakeUnitOfWork(fake_repo),
    )
    monkeypatch.setattr(
        "app.services.event.app_event_bus.get_event_bus",
        lambda: fake_bus,
    )
    return get_agent, save_snapshot, fake_bus


@pytest.mark.asyncio
async def test_force_push_preserves_skill_bindings(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push must not overwrite skill bindings with publisher-side IDs.

    Skill bindings are established by the initial import (which remaps IDs to
    the local store). A force-push carries the publisher's skill_ids, which do
    not exist in the sandbox — copying them would leave the Agent referencing
    skills that are never installed.
    """
    _patch_force_push_dependencies(
        monkeypatch,
        fake_repo,
        existing=FakeExistingAgent("target-1"),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
                "target_agent_id": "target-1",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "target-1"
    assert data["status"] == "force_updated"
    assert data["snapshot_id"] == "snapshot-1"

    assert fake_repo.updated is not None
    assert "skills" not in fake_repo.updated
    assert fake_repo.updated["skill_configs"] == {"publisher-skill-id": {"enabled": True}}
    assert fake_repo.committed


@pytest.mark.asyncio
async def test_force_push_still_applies_config_updates(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push remains a config update path for non-skill fields."""
    _patch_force_push_dependencies(
        monkeypatch,
        fake_repo,
        existing=FakeExistingAgent("target-1"),
    )
    transport = ASGITransport(app=app)

    package = _build_package(
        agent_profile={
            "display_name": "Upgraded Publisher Agent",
            "description": "v2 desc",
            "system_prompt": "New system prompt.",
            "model": "gpt-4.1",
            "model_selection": {"providerId": "openai", "model": "gpt-4.1"},
            "personality_style": "friendly",
            "max_iterations": 25,
            "skill_ids": ["publisher-skill-id"],
            "subagent_ids": [],
            "enabled_builtin_tools": ["web_search"],
            "home_directory": "/home/sandbox",
            "allow_discovery": False,
        },
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": package,
                "force": True,
                "target_agent_id": "target-1",
            },
        )

    assert resp.status_code == 200
    updated = fake_repo.updated
    assert updated is not None
    assert "skills" not in updated
    assert updated["display_name"] == "Upgraded Publisher Agent"
    assert updated["description"] == "v2 desc"
    assert updated["system_prompt"] == "New system prompt."
    assert updated["model"] == "gpt-4.1"
    assert updated["model_selection"] == {"providerId": "openai", "model": "gpt-4.1"}
    assert updated["personality_style"] == "friendly"
    assert updated["max_iterations"] == 25
    assert "tools_allowed" in updated
    metadata = updated.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata["home_directory"] == "/home/sandbox"
    assert metadata["allow_discovery"] is False
    assert "workspace_policy" not in metadata


@pytest.mark.asyncio
async def test_force_push_snapshots_and_publishes_event(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push snapshots the pre-update profile and publishes a config event."""
    _, _, fake_bus = _patch_force_push_dependencies(
        monkeypatch,
        fake_repo,
        existing=FakeExistingAgent("target-1"),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
                "target_agent_id": "target-1",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["snapshot_id"] == "snapshot-1"
    assert data["status"] == "force_updated"

    assert fake_bus.publish.called
    event = fake_bus.publish.call_args.args[0]
    assert event.event_type.value == "agent_config_updated"
    assert event.data == {"agent_id": "target-1", "action": "force_push", "snapshot_id": "snapshot-1"}


@pytest.mark.asyncio
async def test_force_push_resolves_agent_via_marketplace_binding(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push without target_agent_id resolves the Agent via marketplace binding."""
    _patch_force_push_dependencies(
        monkeypatch,
        fake_repo,
        existing=FakeExistingAgent("resolved-1"),
    )
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile._resolve_force_push_agent_id",
        AsyncMock(return_value="resolved-1"),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
                "marketplace_entry_id": "entry-1",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "resolved-1"
    assert data["status"] == "force_updated"


@pytest.mark.asyncio
async def test_force_push_preserves_subagent_bindings(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push must not overwrite subagent bindings with publisher-side IDs.

    Subagent IDs are remapped to local IDs during the initial import; a force-push
    carries the publisher's subagent_ids, which do not exist in the sandbox.
    """
    _patch_force_push_dependencies(
        monkeypatch,
        fake_repo,
        existing=FakeExistingAgent("target-1"),
    )
    transport = ASGITransport(app=app)

    package = _build_package(
        agent_profile={
            "display_name": "Publisher Agent",
            "description": "published desc",
            "system_prompt": "sys",
            "skill_ids": ["publisher-skill-id"],
            "subagent_ids": ["publisher-subagent-id"],
            "enabled_builtin_tools": [],
        },
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": package,
                "force": True,
                "target_agent_id": "target-1",
            },
        )

    assert resp.status_code == 200
    updated = fake_repo.updated
    assert updated is not None
    assert "skills" not in updated
    metadata = updated.get("metadata")
    assert isinstance(metadata, dict)
    assert "subagent_ids" not in metadata


@pytest.mark.asyncio
async def test_force_push_missing_agent_returns_404(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push to a non-existent Agent fails closed with 404."""
    _patch_force_push_dependencies(monkeypatch, fake_repo, existing=None)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
                "target_agent_id": "missing-agent",
            },
        )

    assert resp.status_code == 404
    assert fake_repo.updated is None


@pytest.mark.asyncio
async def test_force_push_missing_binding_returns_400(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
) -> None:
    """Force-push without a target Agent or marketplace binding fails closed."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={
                "package": _build_package(),
                "force": True,
            },
        )

    assert resp.status_code == 400
    assert "marketplace_entry_id" in resp.text


def _set_deploy_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    from app.config.deploy_mode import get_deploy_mode
    from app.platform_utils.deployment_capabilities import (
        _reset_capabilities_cache_for_testing,
    )

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    monkeypatch.setenv("DEPLOY_MODE", mode)
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


@pytest.mark.asyncio
async def test_endpoint_rejects_bundled_skills_in_sandbox(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandbox disables local skills — bundled-skill imports fail closed at the endpoint."""
    _set_deploy_mode(monkeypatch, "sandbox")
    try:
        package = _build_package(
            agent_profile={
                "display_name": "Skilled Publisher Agent",
                "description": "desc",
                "system_prompt": "sys",
                "skill_ids": ["publisher-skill-id"],
                "subagent_ids": [],
                "enabled_builtin_tools": [],
            },
            bundled_skills=[
                {
                    "id": "publisher-skill-id",
                    "name": "publisher-skill",
                    "content": "---\nname: publisher-skill\ndescription: test\n---\n# Skill",
                    "description": "test",
                    "resources": {},
                },
            ],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/import-agent-profile",
                json={"package": package, "force": False},
            )

        assert resp.status_code == 400
        assert "bundled skills are not supported in sandbox" in resp.text
    finally:
        _set_deploy_mode(monkeypatch, "local")
