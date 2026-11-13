"""CustomAgentFactory initialization: the profile's skill backend, MCP configs and the one-time resource setup."""

import asyncio
from types import SimpleNamespace

import pytest

from app.ai_agents.custom_agent_factory import (
    _coerce_str_list,
)


def test_coerce_str_list_keeps_string_items_only() -> None:
    assert _coerce_str_list(["a", 1, "b"]) == ["a", "b"]
    assert _coerce_str_list("not-a-list") == []


@pytest.mark.asyncio
async def test_custom_agent_factory_ensure_initialized(monkeypatch) -> None:
    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(skills=["skill-a"], metadata={"mcp_ids": []})
    factory = CustomAgentFactory(agent_id="agent-init", agent_profile=profile)
    captured_kwargs: dict[str, object] = {}

    async def fake_create_skill_backend(**kwargs: object) -> SimpleNamespace:
        captured_kwargs.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        "app.core.skills.loader.create_skill_backend",
        fake_create_skill_backend,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    async def fake_get_user_skill_config(self: object) -> SimpleNamespace:
        return SimpleNamespace(
            enabled_prebuilt_ids=["alpha-skill"],
            local_skill_paths=[],
            enabled_local_skill_ids=[],
        )

    monkeypatch.setattr(
        "app.core.skills.store.user_config.UserSkillConfigManager.get_config",
        fake_get_user_skill_config,
    )

    await factory._ensure_initialized()
    assert factory._initialized is True
    assert factory._cached_skill_backend is not None
    assert captured_kwargs["allowed_prebuilt_ids"] == frozenset({"alpha-skill"})


@pytest.mark.asyncio
async def test_custom_agent_factory_ensure_initialized_loads_mcp_configs(monkeypatch) -> None:
    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        skills=[],
        metadata={"mcp_ids": ["mcp-a"], "mcp_tool_selections": {}},
    )
    factory = CustomAgentFactory(agent_id="agent-mcp", agent_profile=profile)

    async def fake_create_skill_backend(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace()

    class FakeConfigs:
        mcp_dict = {"mcp-a": {}}
        org_mcp_dict = None

        def providers_dict(self) -> dict[str, object]:
            return {}

    monkeypatch.setattr(
        "app.core.skills.loader.create_skill_backend",
        fake_create_skill_backend,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    async def fake_get_user_skill_config(self: object) -> SimpleNamespace:
        return SimpleNamespace(
            enabled_prebuilt_ids=["mcp-skill"],
            local_skill_paths=[],
            enabled_local_skill_ids=[],
        )

    monkeypatch.setattr(
        "app.core.skills.store.user_config.UserSkillConfigManager.get_config",
        fake_get_user_skill_config,
    )

    async def fake_load_user_configs() -> FakeConfigs:
        return FakeConfigs()

    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        fake_load_user_configs,
    )
    monkeypatch.setattr(
        "app.core.channel_bridge.config_parsers.extract_mcp_configs",
        lambda _mcp_dict: [SimpleNamespace(name="mcp-a")],
    )
    monkeypatch.setattr(
        "app.services.agent.params.mcp_selection.apply_agent_mcp_selection",
        lambda all_mcp, **kwargs: all_mcp,
    )

    await factory._ensure_initialized()
    assert factory._initialized is True
    assert len(factory._cached_mcp_configs) == 1


@pytest.mark.asyncio
async def test_custom_agent_factory_ensure_initialized_tolerates_malformed_prebuilt_ids(monkeypatch) -> None:
    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(skills=["skill-a"], metadata={"mcp_ids": []})
    factory = CustomAgentFactory(agent_id="agent-malformed-prebuilt", agent_profile=profile)
    captured_kwargs: dict[str, object] = {}

    async def fake_create_skill_backend(**kwargs: object) -> SimpleNamespace:
        captured_kwargs.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        "app.core.skills.loader.create_skill_backend",
        fake_create_skill_backend,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    async def fake_get_user_skill_config(self: object) -> SimpleNamespace:
        return SimpleNamespace(
            enabled_prebuilt_ids="not-a-list",
            local_skill_paths=[],
            enabled_local_skill_ids=[],
        )

    monkeypatch.setattr(
        "app.core.skills.store.user_config.UserSkillConfigManager.get_config",
        fake_get_user_skill_config,
    )

    await factory._ensure_initialized()

    assert factory._initialized is True
    assert captured_kwargs["allowed_prebuilt_ids"] == frozenset()


@pytest.mark.asyncio
async def test_custom_agent_factory_ensure_initialized_concurrent_inner_skip(monkeypatch) -> None:
    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(skills=[], metadata={"mcp_ids": []})
    factory = CustomAgentFactory(agent_id="agent-concurrent", agent_profile=profile)

    async def fake_create_skill_backend(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace()

    monkeypatch.setattr(
        "app.core.skills.loader.create_skill_backend",
        fake_create_skill_backend,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    async def fake_get_user_skill_config(self: object) -> SimpleNamespace:
        return SimpleNamespace(
            enabled_prebuilt_ids=["concurrent-skill"],
            local_skill_paths=[],
            enabled_local_skill_ids=[],
        )

    monkeypatch.setattr(
        "app.core.skills.store.user_config.UserSkillConfigManager.get_config",
        fake_get_user_skill_config,
    )

    await asyncio.gather(factory._ensure_initialized(), factory._ensure_initialized())

    assert factory._initialized is True


@pytest.mark.asyncio
async def test_custom_agent_factory_ensure_initialized_mcp_failure_is_non_fatal(monkeypatch) -> None:
    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(skills=[], metadata={"mcp_ids": ["mcp-a"]})
    factory = CustomAgentFactory(agent_id="agent-mcp-fail", agent_profile=profile)

    async def fake_create_skill_backend(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace()

    async def fake_load_user_configs() -> SimpleNamespace:
        raise RuntimeError("mcp load failed")

    monkeypatch.setattr(
        "app.core.skills.loader.create_skill_backend",
        fake_create_skill_backend,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    async def fake_get_user_skill_config(self: object) -> SimpleNamespace:
        return SimpleNamespace(
            enabled_prebuilt_ids=["safe-default"],
            local_skill_paths=[],
            enabled_local_skill_ids=[],
        )

    monkeypatch.setattr(
        "app.core.skills.store.user_config.UserSkillConfigManager.get_config",
        fake_get_user_skill_config,
    )
    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        fake_load_user_configs,
    )

    await factory._ensure_initialized()

    assert factory._initialized is True
    assert factory._cached_mcp_configs == []
