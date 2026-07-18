"""Unit tests for marketplace_import module.

Tests cover:
- Full import flow with skill/subagent/agent creation
- Skill ID remapping
- Subagent ID remapping + skill_ids remapping within subagents
- Idempotent subagent de-duplication by stable origin key
- Contract fail-closed validation (malformed/tampered package rejected)
- Transport signature trust gate
- Atomic rollback on import failure
- Empty package import
- _remap_ids preserves unmapped IDs
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest


@dataclass
class FakeSkillSaveResult:
    success: bool
    skill_id: str = ""
    skill_name: str = ""
    saved_path: str = ""
    was_updated: bool = False
    error: str = ""


@dataclass
class FakeAgentProfile:
    id: str
    display_name: str | None = None
    metadata: dict[str, object] | None = None


@dataclass
class FakeSkillDeleteResult:
    success: bool
    skill_name: str = ""
    error: str = ""


@dataclass
class FakeSkillResourceWriteResult:
    success: bool
    skill_name: str = ""
    resource_path: str = ""
    error: str = ""


class FakeSkillSaveResultNoWasUpdated:
    success = True
    skill_id = "local::new-skill-hash"
    error = ""


def _make_package(
    *,
    agent_profile: dict[str, object] | None = None,
    bundled_skills: list[dict[str, object]] | None = None,
    bundled_subagents: list[dict[str, object]] | None = None,
    transport_secret: str | None = None,
) -> dict[str, object]:
    from app.services.agent.marketplace_package_contract import (
        apply_marketplace_transport_signature,
        build_marketplace_package,
    )

    package = build_marketplace_package(
        agent_profile=agent_profile
        or {
            "display_name": "Test Agent",
            "description": "desc",
            "system_prompt": "sys",
            "skill_ids": ["old-skill-1"],
            "subagent_ids": ["old-sub-1"],
            "enabled_builtin_tools": [],
            "personality_style": "professional",
        },
        bundled_skills=bundled_skills
        if bundled_skills is not None
        else [
            {
                "id": "old-skill-1",
                "name": "sales-skill",
                "content": "# Sales Skill\nPrompt here.",
                "description": "Sales helper",
                "resources": {"data.json": '{"key": "val"}'},
            },
        ],
        bundled_mcp_configs=[],
        bundled_subagents=bundled_subagents
        if bundled_subagents is not None
        else [
            {
                "original_id": "old-sub-1",
                "profile": {
                    "display_name": "Sub Agent",
                    "description": "sub desc",
                    "system_prompt": "sub sys",
                    "skill_ids": ["old-skill-1"],
                    "enabled_builtin_tools": [],
                },
            },
        ],
    )
    if transport_secret is not None:
        return apply_marketplace_transport_signature(
            package,
            transport_secret=transport_secret,
        )
    return package


@pytest.fixture
def mock_skill_svc() -> AsyncMock:
    svc = AsyncMock()
    svc.save_skill = AsyncMock(return_value=FakeSkillSaveResult(
        success=True,
        skill_id="local::new-skill-hash",
        skill_name="sales-skill",
    ))
    svc.write_resource = AsyncMock(return_value=FakeSkillResourceWriteResult(success=True))
    svc.delete_skill = AsyncMock(return_value=FakeSkillDeleteResult(success=True))
    svc.base_path = None
    return svc


_AGENT_SVC_PATH = "app.services.agent.agent_service.AgentService"


@pytest.fixture
def patch_agent_service():
    """Patch AgentService class methods used by marketplace_import."""
    with patch(
        f"{_AGENT_SVC_PATH}.create_agent",
        new_callable=AsyncMock,
        side_effect=lambda data: FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def patch_marketplace_origin_helpers():
    with patch(
        "app.services.agent.marketplace_import._find_existing_subagent_by_origin_key",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.mark.asyncio
async def test_full_import_flow(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Full import: skills installed, IDs remapped, subagent + agent created."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    result = await import_agent_package(mock_skill_svc, package)

    mock_skill_svc.save_skill.assert_called_once_with(
        "sales-skill", "# Sales Skill\nPrompt here.", "Sales helper"
    )
    mock_skill_svc.write_resource.assert_called_once_with(
        "sales-skill", "data.json", '{"key": "val"}'
    )
    assert result == "new-test-agent"


@pytest.mark.asyncio
async def test_skill_id_remapping(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Agent's skill_ids are remapped from old to new IDs."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(bundled_subagents=[])
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(id="new-agent", display_name=data.name)

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    assert len(created_data) == 1
    assert created_data[0].skill_ids == ["local::new-skill-hash"]


@pytest.mark.asyncio
async def test_subagent_skill_ids_remapped(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Subagent's skill_ids also get remapped."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        )

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    sub_data = created_data[0]
    assert sub_data.name == "Sub Agent"
    assert sub_data.skill_ids == ["local::new-skill-hash"]


@pytest.mark.asyncio
async def test_subagent_idempotent_dedup(mock_skill_svc: AsyncMock):
    """Existing subagent with same origin key is reused (not created again)."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        )

    with patch(
        "app.services.agent.marketplace_import._find_existing_subagent_by_origin_key",
        new_callable=AsyncMock,
        return_value="existing-sub-id",
    ), patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    assert len(created_data) == 1
    main_agent_data = created_data[0]
    assert main_agent_data.name == "Test Agent"
    assert "existing-sub-id" in main_agent_data.subagent_ids


@pytest.mark.asyncio
async def test_malformed_skill_rejected(mock_skill_svc: AsyncMock):
    """Malformed skill contract should fail-closed before any writes."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(bundled_skills=[], bundled_subagents=[])
    package["bundled_skills"] = [
        {"id": "bad-1", "name": "", "content": "has content"},
        {"id": "bad-2", "name": "has-name", "content": ""},
    ]
    with pytest.raises(ValueError, match="bundled_skills.name"):
        await import_agent_package(mock_skill_svc, package)
    mock_skill_svc.save_skill.assert_not_called()


@pytest.mark.asyncio
async def test_save_skill_failure_aborts_import(mock_skill_svc: AsyncMock):
    """save_skill failure should abort import (fail-closed)."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    mock_skill_svc.save_skill = AsyncMock(
        return_value=FakeSkillSaveResult(success=False, error="disk full")
    )

    package = _make_package(bundled_subagents=[])
    with patch.object(AgentService, "create_agent", new_callable=AsyncMock) as create_mock:
        with pytest.raises(ValueError, match="failed to save skill"):
            await import_agent_package(mock_skill_svc, package)
    create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_save_skill_missing_was_updated_flag_rejected(mock_skill_svc: AsyncMock):
    """Skill backend must return was_updated to guarantee rollback safety."""
    from app.services.agent.marketplace_import import import_agent_package

    mock_skill_svc.save_skill = AsyncMock(return_value=FakeSkillSaveResultNoWasUpdated())
    package = _make_package(bundled_subagents=[])

    with pytest.raises(RuntimeError, match="did not return 'was_updated'"):
        await import_agent_package(mock_skill_svc, package)
    mock_skill_svc.delete_skill.assert_not_called()


@pytest.mark.asyncio
async def test_empty_package(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Empty package creates agent with defaults."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        agent_profile={"display_name": "Empty Agent"},
        bundled_skills=[],
        bundled_subagents=[],
    )
    result = await import_agent_package(mock_skill_svc, package)
    assert result == "new-empty-agent"
    mock_skill_svc.save_skill.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_tampered_package_digest(mock_skill_svc: AsyncMock):
    """Tampered trust digest should be rejected by integrity gate."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    trust = package["trust"]
    assert isinstance(trust, dict)
    trust["payload_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="integrity check failed"):
        await import_agent_package(mock_skill_svc, package)
    mock_skill_svc.save_skill.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_missing_transport_signature_when_required(mock_skill_svc: AsyncMock):
    """Require transport signature should reject unsigned package."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(bundled_subagents=[])
    with pytest.raises(ValueError, match="missing transport signature"):
        await import_agent_package(
            mock_skill_svc,
            package,
            require_transport_signature=True,
            transport_secret="cp-sign-secret",
        )


@pytest.mark.asyncio
async def test_accepts_transport_signature_when_required(
    mock_skill_svc: AsyncMock,
    patch_agent_service: None,
):
    """Signed package should pass when transport signature is required."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        bundled_subagents=[],
        transport_secret="cp-sign-secret",
    )
    result = await import_agent_package(
        mock_skill_svc,
        package,
        require_transport_signature=True,
        transport_secret="cp-sign-secret",
    )
    assert result == "new-test-agent"


@pytest.mark.asyncio
async def test_subagent_origin_key_persisted_on_create(
    mock_skill_svc: AsyncMock,
):
    """Newly created subagent should carry stable origin key in engine_params."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        )

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    assert len(created_data) == 2
    subagent_data = created_data[0]
    assert isinstance(subagent_data.engine_params, dict)
    origin_key = subagent_data.engine_params.get("marketplace_subagent_origin_key")
    assert isinstance(origin_key, str)
    assert origin_key.endswith(":old-sub-1")


@pytest.mark.asyncio
async def test_subagent_origin_index_loaded_once_per_import(mock_skill_svc: AsyncMock):
    """Subagent origin lookup should build index once per import run."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        agent_profile={
            "display_name": "Parent Agent",
            "description": "parent",
            "system_prompt": "sys",
            "skill_ids": [],
            "subagent_ids": ["old-sub-1", "old-sub-2"],
            "enabled_builtin_tools": [],
            "personality_style": "professional",
        },
        bundled_skills=[],
        bundled_subagents=[
            {
                "original_id": "old-sub-1",
                "profile": {
                    "display_name": "Sub Agent 1",
                    "description": "sub",
                    "system_prompt": "sys",
                    "skill_ids": [],
                    "enabled_builtin_tools": [],
                },
            },
            {
                "original_id": "old-sub-2",
                "profile": {
                    "display_name": "Sub Agent 2",
                    "description": "sub",
                    "system_prompt": "sys",
                    "skill_ids": [],
                    "enabled_builtin_tools": [],
                },
            },
        ],
    )
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        )

    with patch(
        "app.services.agent.marketplace_import._load_subagent_origin_index",
        new_callable=AsyncMock,
        return_value={},
    ) as load_origin_index_mock, patch(
        "app.services.agent.marketplace_import._find_existing_subagent_by_origin_key",
        new_callable=AsyncMock,
        side_effect=lambda origin_key, origin_index=None: (
            origin_index.get(origin_key)
            if isinstance(origin_index, dict)
            else None
        ),
    ), patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    load_origin_index_mock.assert_awaited_once()
    assert len(created_data) == 3


@pytest.mark.asyncio
async def test_main_agent_binds_marketplace_entry_id(mock_skill_svc: AsyncMock):
    """Main agent should persist marketplace entry binding in engine_params."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        bundled_subagents=[],
        bundled_skills=[],
        agent_profile={
            "display_name": "Bound Agent",
            "description": "bound",
            "system_prompt": "sys",
            "skill_ids": [],
            "subagent_ids": [],
            "enabled_builtin_tools": [],
        },
    )
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(id="new-bound-agent", display_name=data.name)

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(
            mock_skill_svc,
            package,
            marketplace_entry_id="entry-abc123",
        )

    assert len(created_data) == 1
    created = created_data[0]
    assert isinstance(created.engine_params, dict)
    assert created.engine_params.get("marketplace_entry_id") == "entry-abc123"


@pytest.mark.asyncio
async def test_profile_fidelity_fields_mapped(mock_skill_svc: AsyncMock):
    """Import should preserve high-value profile fields beyond base IDs."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        agent_profile={
            "display_name": "Rich Agent",
            "description": "rich desc",
            "system_prompt": "rich prompt",
            "skill_ids": [],
            "subagent_ids": [],
            "enabled_builtin_tools": ["web_search"],
            "personality_style": "professional",
            "model_selection": {"providerId": "openai", "model": "gpt-4.1"},
            "workspace_policy": "READ_ONLY_SANDBOX",
            "engine_params": {"max_tool_calls": 7},
            "auto_restore_domains": ["example.com"],
            "openapi_services": [{"name": "weather", "schema": {"openapi": "3.0.0"}}],
            "command_bindings": [{
                "command_name": "daily-report",
                "skill_ids": [],
                "description": "desc",
                "aliases": ["report"],
                "instruction": "run",
            }],
            "security_overrides": {"allow_bash": False},
            "prompt_mode": "lean",
            "notify_targets": [{"channel": "slack", "recipient_id": "U123"}],
            "browser_source": "auto",
            "dialog_policy": "smart",
            "session_recording": "off",
            "cron_post_run_verify": True,
        },
        bundled_skills=[],
        bundled_subagents=[],
    )
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(id="new-rich-agent", display_name=data.name)

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    assert len(created_data) == 1
    created = created_data[0]
    assert created.model_selection is not None
    assert created.model_selection.model == "gpt-4.1"
    assert created.workspace_policy == "READ_ONLY_SANDBOX"
    assert created.engine_params == {"max_tool_calls": 7}
    assert created.auto_restore_domains == ["example.com"]
    assert created.openapi_services == [{"name": "weather", "schema": {"openapi": "3.0.0"}}]
    assert created.command_bindings is not None
    assert created.command_bindings[0].command_name == "daily-report"
    assert created.security_overrides == {"allow_bash": False}
    assert created.prompt_mode == "lean"
    assert created.notify_targets == [{"channel": "slack", "recipient_id": "U123"}]
    assert created.browser_source == "auto"
    assert created.dialog_policy == "smart"
    assert created.session_recording == "off"
    assert created.cron_post_run_verify is True


@pytest.mark.asyncio
async def test_atomic_rollback_skills_when_main_agent_creation_fails(mock_skill_svc: AsyncMock):
    """When main Agent creation fails, imported skills must be rolled back."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(bundled_subagents=[])

    with patch.object(
        AgentService,
        "create_agent",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        with pytest.raises(RuntimeError, match="db down"):
            await import_agent_package(mock_skill_svc, package)

    mock_skill_svc.delete_skill.assert_awaited_once_with("sales-skill")


@pytest.mark.asyncio
async def test_atomic_rollback_subagent_and_skill_when_main_creation_fails(mock_skill_svc: AsyncMock):
    """Rollback should delete newly created subagent + skill when main create fails."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    create_side_effect = [
        FakeAgentProfile(id="new-subagent-id", display_name="Sub Agent"),
        RuntimeError("main create failed"),
    ]

    with patch.object(
        AgentService,
        "create_agent",
        new=AsyncMock(side_effect=create_side_effect),
    ), patch.object(
        AgentService,
        "delete_agent",
        new=AsyncMock(return_value=True),
    ) as delete_agent_mock:
        with pytest.raises(RuntimeError, match="main create failed"):
            await import_agent_package(mock_skill_svc, package)

    delete_agent_mock.assert_awaited_once_with("new-subagent-id")
    mock_skill_svc.delete_skill.assert_awaited_once_with("sales-skill")


@pytest.mark.asyncio
async def test_remap_ids_preserves_unmapped():
    """_remap_ids preserves IDs not in the mapping."""
    from app.services.agent.marketplace_import import _remap_ids

    profile = {
        "skill_ids": ["mapped-1", "unknown-2"],
        "subagent_ids": ["mapped-sub", "unknown-sub"],
    }
    skill_map = {"mapped-1": "new-1"}
    sub_map = {"mapped-sub": "new-sub"}

    result = _remap_ids(profile, skill_map, sub_map)

    assert result["skill_ids"] == ["new-1", "unknown-2"]
    assert result["subagent_ids"] == ["new-sub", "unknown-sub"]
