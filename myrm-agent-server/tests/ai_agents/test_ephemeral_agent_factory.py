"""EphemeralAgentFactory: build path and memory_search_tool rebinding for in-memory subagents."""

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_rebinds_memory_search_tool(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    class FakeMemoryManager:
        approval_required = False

    captured_tools: list[object] = []

    def fake_create_memory_tools(
        manager: object,
        recall_mode: object = None,
        *,
        search_policy: object = None,
        search_backends: object = None,
        description_locale: str | None = None,
    ) -> list[object]:
        return [SimpleNamespace(name="memory_search_tool", marker="rebound")]

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        tools = kwargs.get("tools")
        if isinstance(tools, list):
            captured_tools.extend(tools)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module
    import myrm_agent_harness.toolkits as toolkits_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(toolkits_module, "create_memory_tools", fake_create_memory_tools)
    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)
    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)

    factory = EphemeralAgentFactory(
        agent_id="researcher",
        metadata={"enabled_builtin_tools": ["memory", "web_search"]},
    )
    parent = SimpleNamespace(
        enable_conversation_search=True,
        incognito_mode=False,
        enable_wiki=False,
        llm=None,
        executor=None,
        memory_manager=FakeMemoryManager(),
        _last_context={"chat_id": "chat-ephemeral"},
    )
    config = SubagentConfig(display_name="Researcher", system_prompt="You research.")
    inherited_tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]

    await factory.build(
        config,
        inherited_tools,
        "Find prior pricing notes",
        parent,
        current_depth=1,
    )

    assert len(captured_tools) == 1
    assert captured_tools[0].name == "memory_search_tool"
    assert captured_tools[0].marker == "rebound"


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_keeps_parent_tool_without_memory_group(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    captured_tools: list[object] = []

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        tools = kwargs.get("tools")
        if isinstance(tools, list):
            captured_tools.extend(tools)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)

    factory = EphemeralAgentFactory(
        agent_id="researcher",
        metadata={"enabled_builtin_tools": ["web_search"]},
    )
    parent = SimpleNamespace(
        enable_conversation_search=True,
        incognito_mode=False,
        enable_wiki=False,
        llm=None,
        executor=None,
        memory_manager=SimpleNamespace(),
        _last_context={"chat_id": "chat-ephemeral"},
    )
    config = SubagentConfig(display_name="Researcher", system_prompt="You research.")
    inherited_tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]

    await factory.build(
        config,
        inherited_tools,
        "Find prior pricing notes",
        parent,
        current_depth=1,
    )

    assert captured_tools == []


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_passes_write_backend_for_skill_manage_tool(
    monkeypatch,
) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    captured_kwargs: dict[str, object] = {}

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        captured_kwargs.update(kwargs)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)

    factory = EphemeralAgentFactory(
        agent_id="skill-author",
        metadata={"enabled_builtin_tools": ["web_search"]},
    )
    parent = SimpleNamespace(
        llm=SimpleNamespace(),
        executor=SimpleNamespace(),
        memory_manager=None,
    )
    config = SubagentConfig(
        display_name="Author",
        system_prompt="You write skills.",
        tools=["skill_manage_tool"],
    )

    await factory.build(
        config,
        [],
        "Create a reusable skill from this workflow",
        parent,
        current_depth=1,
    )

    assert captured_kwargs.get("write_backend") is not None


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_fork_context_clears_system_prompt(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    captured_spec: list[object] = []

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        spec = kwargs.get("spec")
        if spec is not None:
            captured_spec.append(spec)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    factory = EphemeralAgentFactory(agent_id="fork-agent", metadata={})
    parent = SimpleNamespace(
        llm=SimpleNamespace(),
        executor=None,
        memory_manager=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-fork"},
    )
    config = SubagentConfig(
        display_name="Fork",
        system_prompt="Should be dropped",
        context_mode="fork",
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_spec
    assert captured_spec[0].system_prompt == ""


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_uses_config_llm(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    direct_llm = SimpleNamespace(model="ephemeral-direct")
    captured_llm: list[object] = []

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        llm = kwargs.get("llm")
        if llm is not None:
            captured_llm.append(llm)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    factory = EphemeralAgentFactory(agent_id="ephemeral-llm", metadata={})
    parent = SimpleNamespace(
        llm=SimpleNamespace(model="parent"),
        executor=None,
        memory_manager=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-ephemeral-llm"},
    )
    config = SubagentConfig(
        display_name="Ephemeral Direct",
        system_prompt="Use direct llm.",
        llm=direct_llm,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_llm == [direct_llm]


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_resolves_model_from_config(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    resolved_llm = SimpleNamespace(model="ephemeral-resolved")
    captured_llm: list[object] = []

    async def fake_load_user_configs() -> SimpleNamespace:
        return SimpleNamespace(providers_dict={"openai": {}})

    async def fake_get_llm_from_config(*args: object, **kwargs: object) -> SimpleNamespace:
        return resolved_llm

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        llm = kwargs.get("llm")
        if llm is not None:
            captured_llm.append(llm)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        fake_load_user_configs,
    )
    monkeypatch.setattr(
        "app.core.channel_bridge.model_resolver.resolve_model_config",
        lambda providers_dict, **kwargs: SimpleNamespace(api_keys=None),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
        fake_get_llm_from_config,
    )
    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    factory = EphemeralAgentFactory(agent_id="ephemeral-model", metadata={})
    parent = SimpleNamespace(
        llm=SimpleNamespace(model="parent"),
        executor=None,
        memory_manager=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-ephemeral-model"},
    )
    config = SubagentConfig(
        display_name="Ephemeral Resolved",
        system_prompt="Resolve model.",
        model="gpt-ephemeral",
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_llm == [resolved_llm]


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_model_resolution_failure_falls_back(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.ephemeral_agent_factory import EphemeralAgentFactory

    parent_llm = SimpleNamespace(model="parent")
    captured_llm: list[object] = []

    async def fake_load_user_configs() -> SimpleNamespace:
        raise RuntimeError("ephemeral model resolution failed")

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        llm = kwargs.get("llm")
        if llm is not None:
            captured_llm.append(llm)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        fake_load_user_configs,
    )
    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    factory = EphemeralAgentFactory(agent_id="ephemeral-fallback", metadata={})
    parent = SimpleNamespace(
        llm=parent_llm,
        executor=None,
        memory_manager=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-ephemeral-fallback"},
    )
    config = SubagentConfig(
        display_name="Ephemeral Fallback",
        system_prompt="Fallback to parent.",
        model="missing-model",
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_llm == [parent_llm]
