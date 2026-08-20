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
    assert event.data == {
        "agent_id": "target-1",
        "action": "force_push",
        "snapshot_id": "snapshot-1",
    }


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


@pytest.mark.asyncio
async def test_force_push_unresolved_binding_returns_404(
    app: FastAPI,
    fake_repo: FakeAgentRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force-push with an entry_id that matches no local Agent fails closed with 404."""
    _patch_force_push_dependencies(
        monkeypatch,
        fake_repo,
        existing=None,
    )
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile._resolve_force_push_agent_id",
        AsyncMock(return_value=None),
    )
    transport = ASGITransport(app=app)

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
    assert fake_repo.updated is None


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


class TestVerifyCpToken:
    def test_rejects_wrong_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi import HTTPException

        from app.api.internal.import_agent_profile import _verify_cp_token

        monkeypatch.setenv("CONTROL_PLANE_TELEMETRY_TOKEN", "correct")
        request = MagicMock()
        request.headers.get.return_value = "wrong"

        with pytest.raises(HTTPException) as exc_info:
            _verify_cp_token(request)

        assert exc_info.value.status_code == 403

    def test_accepts_correct_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api.internal.import_agent_profile import _verify_cp_token

        monkeypatch.setenv("CONTROL_PLANE_TELEMETRY_TOKEN", "correct")
        request = MagicMock()
        request.headers.get.return_value = "correct"

        _verify_cp_token(request)

    def test_skips_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api.internal.import_agent_profile import _verify_cp_token

        monkeypatch.delenv("CONTROL_PLANE_TELEMETRY_TOKEN", raising=False)
        _verify_cp_token(MagicMock())


class TestEnvFlag:
    def test_default_when_none(self) -> None:
        from app.api.internal.import_agent_profile import _env_flag

        assert _env_flag(None, default=True) is True
        assert _env_flag(None, default=False) is False

    def test_parses_truthy(self) -> None:
        from app.api.internal.import_agent_profile import _env_flag

        for value in ("1", "true", "yes", "on", "TRUE"):
            assert _env_flag(value, default=False) is True

    def test_parses_falsy(self) -> None:
        from app.api.internal.import_agent_profile import _env_flag

        for value in ("0", "false", "no", "off", "FALSE"):
            assert _env_flag(value, default=True) is False

    def test_default_on_unknown(self) -> None:
        from app.api.internal.import_agent_profile import _env_flag

        assert _env_flag("maybe", default=True) is True


class TestExtractModelUpdate:
    def test_uses_model_selection(self) -> None:
        from app.api.internal.import_agent_profile import _extract_model_update

        model, selection = _extract_model_update({"model_selection": {"providerId": "openai", "model": "gpt-4.1"}})
        assert model == "gpt-4.1"
        assert selection == {"providerId": "openai", "model": "gpt-4.1"}

    def test_falls_back_to_model(self) -> None:
        from app.api.internal.import_agent_profile import _extract_model_update

        model, selection = _extract_model_update({"model": "gpt-4o"})
        assert model == "gpt-4o"
        assert selection == {"providerId": "auto", "model": "gpt-4o"}

    def test_returns_none_when_absent(self) -> None:
        from app.api.internal.import_agent_profile import _extract_model_update

        assert _extract_model_update({}) == (None, None)


class TestNormalizeMarketplaceEntryId:
    def test_strips_whitespace(self) -> None:
        from app.api.internal.import_agent_profile import (
            _normalize_marketplace_entry_id,
        )

        assert _normalize_marketplace_entry_id("  entry-1  ") == "entry-1"

    def test_none_passes_through(self) -> None:
        from app.api.internal.import_agent_profile import (
            _normalize_marketplace_entry_id,
        )

        assert _normalize_marketplace_entry_id(None) is None

    def test_empty_raises_400(self) -> None:
        from fastapi import HTTPException

        from app.api.internal.import_agent_profile import (
            _normalize_marketplace_entry_id,
        )

        with pytest.raises(HTTPException) as exc_info:
            _normalize_marketplace_entry_id("   ")
        assert exc_info.value.status_code == 400


class TestResolveForcePushAgentId:
    @pytest.fixture
    def list_repo(self) -> FakeAgentRepo:
        return FakeAgentRepo()

    @pytest.mark.asyncio
    async def test_resolves_single_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api.internal.import_agent_profile import _resolve_force_push_agent_id

        repo = MagicMock()
        repo.list_profiles = AsyncMock(
            return_value=[
                MagicMock(
                    id="p1",
                    metadata={"engine_params": {"marketplace_entry_id": "entry-1"}},
                ),
                MagicMock(
                    id="p2",
                    metadata={"engine_params": {"marketplace_entry_id": "other"}},
                ),
            ]
        )
        fake_uow = MagicMock()
        fake_uow.__aenter__ = AsyncMock(return_value=fake_uow)
        fake_uow.__aexit__ = AsyncMock(return_value=None)
        fake_uow.agent_repo = repo
        monkeypatch.setattr("app.api.internal.import_agent_profile.UnitOfWork", lambda: fake_uow)

        assert await _resolve_force_push_agent_id("entry-1") == "p1"

    @pytest.mark.asyncio
    async def test_returns_none_without_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.api.internal.import_agent_profile import _resolve_force_push_agent_id

        repo = MagicMock()
        repo.list_profiles = AsyncMock(return_value=[])
        fake_uow = MagicMock()
        fake_uow.__aenter__ = AsyncMock(return_value=fake_uow)
        fake_uow.__aexit__ = AsyncMock(return_value=None)
        fake_uow.agent_repo = repo
        monkeypatch.setattr("app.api.internal.import_agent_profile.UnitOfWork", lambda: fake_uow)

        assert await _resolve_force_push_agent_id("entry-1") is None

    @pytest.mark.asyncio
    async def test_skips_profiles_without_dict_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Profiles whose metadata is not a dict are skipped, not fatal."""
        from app.api.internal.import_agent_profile import _resolve_force_push_agent_id

        repo = MagicMock()
        repo.list_profiles = AsyncMock(
            return_value=[
                MagicMock(id="skip", metadata=None),
                MagicMock(id="p1", metadata={"engine_params": {"marketplace_entry_id": "entry-1"}}),
            ]
        )
        fake_uow = MagicMock()
        fake_uow.__aenter__ = AsyncMock(return_value=fake_uow)
        fake_uow.__aexit__ = AsyncMock(return_value=None)
        fake_uow.agent_repo = repo
        monkeypatch.setattr("app.api.internal.import_agent_profile.UnitOfWork", lambda: fake_uow)

        assert await _resolve_force_push_agent_id("entry-1") == "p1"

    @pytest.mark.asyncio
    async def test_skips_profiles_without_dict_engine_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Profiles whose engine_params is not a dict are skipped, not fatal."""
        from app.api.internal.import_agent_profile import _resolve_force_push_agent_id

        repo = MagicMock()
        repo.list_profiles = AsyncMock(
            return_value=[
                MagicMock(id="skip", metadata={"engine_params": None}),
                MagicMock(id="p1", metadata={"engine_params": {"marketplace_entry_id": "entry-1"}}),
            ]
        )
        fake_uow = MagicMock()
        fake_uow.__aenter__ = AsyncMock(return_value=fake_uow)
        fake_uow.__aexit__ = AsyncMock(return_value=None)
        fake_uow.agent_repo = repo
        monkeypatch.setattr("app.api.internal.import_agent_profile.UnitOfWork", lambda: fake_uow)

        assert await _resolve_force_push_agent_id("entry-1") == "p1"

    @pytest.mark.asyncio
    async def test_ambiguous_match_raises_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi import HTTPException

        from app.api.internal.import_agent_profile import _resolve_force_push_agent_id

        repo = MagicMock()
        repo.list_profiles = AsyncMock(
            return_value=[
                MagicMock(
                    id="p1",
                    metadata={"engine_params": {"marketplace_entry_id": "entry-1"}},
                ),
                MagicMock(
                    id="p2",
                    metadata={"engine_params": {"marketplace_entry_id": "entry-1"}},
                ),
            ]
        )
        fake_uow = MagicMock()
        fake_uow.__aenter__ = AsyncMock(return_value=fake_uow)
        fake_uow.__aexit__ = AsyncMock(return_value=None)
        fake_uow.agent_repo = repo
        monkeypatch.setattr("app.api.internal.import_agent_profile.UnitOfWork", lambda: fake_uow)

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_force_push_agent_id("entry-1")
        assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_non_force_import_installs(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain (non-force) import returns the installed agent."""
    package = _build_package()
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile.validate_marketplace_package",
        MagicMock(return_value=MagicMock(model_dump=MagicMock(return_value=package))),
    )
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile.import_agent_package",
        AsyncMock(return_value="new-agent-1"),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={"package": package, "force": False},
        )

    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "new-agent-1"
    assert resp.json()["status"] == "installed"


@pytest.mark.asyncio
async def test_import_failure_returns_500(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected import failures are wrapped as HTTP 500."""
    package = _build_package()
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile.validate_marketplace_package",
        MagicMock(return_value=MagicMock(model_dump=MagicMock(return_value=package))),
    )
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile.import_agent_package",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={"package": package, "force": False},
        )

    assert resp.status_code == 500
    assert "Import failed" in resp.text


@pytest.mark.asyncio
async def test_empty_marketplace_entry_id_returns_400(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only marketplace_entry_id is rejected."""
    package = _build_package()
    monkeypatch.setattr(
        "app.api.internal.import_agent_profile.validate_marketplace_package",
        MagicMock(return_value=MagicMock(model_dump=MagicMock(return_value=package))),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/admin/import-agent-profile",
            json={"package": package, "force": True, "marketplace_entry_id": "   "},
        )

    assert resp.status_code == 400
    assert "marketplace_entry_id" in resp.text
