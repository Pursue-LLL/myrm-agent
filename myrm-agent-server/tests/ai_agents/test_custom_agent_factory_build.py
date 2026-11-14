"""CustomAgentFactory build path: LLM and model resolution, memory, MCP runtime configs and fork context."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_custom_agent_factory_build_rebinds_memory_search_tool(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    class FakeMemoryManager:
        approval_required = False

    profile = SimpleNamespace(
        display_name="Custom Researcher",
        skills=[],
        enabled_builtin_tools=("memory", "bash"),
        max_iterations=12,
        memory_policy=None,
    )
    factory = CustomAgentFactory(agent_id="custom-researcher", agent_profile=profile)
    factory._initialized = True
    factory._cached_mcp_configs = []
    factory._cached_skill_backend = None

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

    async def fake_create_memory_manager(*args: object, **kwargs: object) -> FakeMemoryManager:
        return FakeMemoryManager()

    async def fake_load_platform_retrieval_configs() -> tuple[object, None]:
        return (SimpleNamespace(), None)

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
    monkeypatch.setattr(
        "app.core.memory.adapters.setup.create_memory_manager",
        fake_create_memory_manager,
    )
    monkeypatch.setattr(
        "app.services.agent.platform_config.load_platform_retrieval_configs",
        fake_load_platform_retrieval_configs,
    )
    monkeypatch.setattr(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    parent = SimpleNamespace(
        enable_conversation_search=True,
        incognito_mode=False,
        enable_wiki=False,
        llm=SimpleNamespace(),
        executor=SimpleNamespace(),
        _last_context={"chat_id": "chat-custom"},
    )
    config = SubagentConfig(
        display_name="Researcher",
        system_prompt="You research.",
        memory_isolation=MemoryIsolationPolicy.COLLABORATIVE_SESSION,
    )
    inherited_tools: list[object] = [
        SimpleNamespace(name="memory_search_tool", marker="parent"),
        SimpleNamespace(name="bash"),
    ]

    agent = await factory.build(
        config,
        inherited_tools,
        "Find prior notes",
        parent,
        current_depth=1,
    )

    assert agent is not None
    assert len(captured_tools) == 2
    rebound = next(tool for tool in captured_tools if tool.name == "memory_search_tool")
    assert rebound.marker == "rebound"


@pytest.mark.asyncio
async def test_custom_agent_factory_build_fork_context_clears_system_prompt(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Fork Custom",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="custom-fork", agent_profile=profile)
    factory._initialized = True

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

    parent = SimpleNamespace(
        llm=SimpleNamespace(),
        executor=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-fork-custom"},
    )
    config = SubagentConfig(
        display_name="Fork",
        system_prompt="drop-me",
        context_mode="fork",
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_spec
    assert captured_spec[0].system_prompt == ""


@pytest.mark.asyncio
async def test_custom_agent_factory_build_prepares_mcp_runtime_configs(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="MCP Subagent",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={
            "engine_params": {"mcp_surface_mode": "catalog_invoke"},
            "openapi_services": [{"name": "svc-a", "enabled": True}],
        },
    )
    factory = CustomAgentFactory(agent_id="custom-mcp-prepare", agent_profile=profile)
    factory._initialized = True
    factory._cached_mcp_configs = [SimpleNamespace(name="mcp-a")]
    factory._cached_skill_backend = None

    prepared_mcp = [SimpleNamespace(name="mcp-a-prepared")]
    prepare_mock = AsyncMock(return_value=prepared_mcp)
    monkeypatch.setattr(
        "app.services.agent.mcp_runtime_prepare.prepare_mcp_configs_for_runtime",
        prepare_mock,
    )

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

    parent = SimpleNamespace(
        llm=SimpleNamespace(),
        executor=SimpleNamespace(),
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-mcp-prepare"},
    )
    config = SubagentConfig(
        display_name="MCP Worker",
        system_prompt="Use MCP tools.",
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "Call MCP", parent, current_depth=1)

    prepare_mock.assert_awaited_once_with("custom-mcp-prepare", factory._cached_mcp_configs)
    assert captured_spec
    spec = captured_spec[0]
    assert spec.mcp_servers == prepared_mcp
    assert spec.mcp_surface_mode == "auto"
    assert spec.engine_params == {"mcp_surface_mode": "auto"}
    assert spec.openapi_services == [{"name": "svc-a", "enabled": True}]


@pytest.mark.asyncio
async def test_custom_agent_factory_build_uses_config_llm(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Direct LLM",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="custom-llm", agent_profile=profile)
    factory._initialized = True

    direct_llm = SimpleNamespace(model="direct")
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

    parent = SimpleNamespace(
        llm=SimpleNamespace(model="parent"),
        executor=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-llm"},
    )
    config = SubagentConfig(
        display_name="Direct",
        system_prompt="Use direct llm.",
        llm=direct_llm,
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_llm == [direct_llm]


@pytest.mark.asyncio
async def test_custom_agent_factory_build_resolves_model_from_config(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Resolved LLM",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="custom-model", agent_profile=profile)
    factory._initialized = True

    resolved_llm = SimpleNamespace(model="resolved")
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

    parent = SimpleNamespace(
        llm=SimpleNamespace(model="parent"),
        executor=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-model"},
    )
    config = SubagentConfig(
        display_name="Resolved",
        system_prompt="Resolve model.",
        model="gpt-test",
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_llm == [resolved_llm]


@pytest.mark.asyncio
async def test_custom_agent_factory_build_model_resolution_failure_falls_back(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Fallback LLM",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="custom-fallback", agent_profile=profile)
    factory._initialized = True

    parent_llm = SimpleNamespace(model="parent")
    captured_llm: list[object] = []

    async def fake_load_user_configs() -> SimpleNamespace:
        raise RuntimeError("model resolution failed")

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

    parent = SimpleNamespace(
        llm=parent_llm,
        executor=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-fallback"},
    )
    config = SubagentConfig(
        display_name="Fallback",
        system_prompt="Fallback to parent.",
        model="missing-model",
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_llm == [parent_llm]


@pytest.mark.asyncio
async def test_custom_agent_factory_build_memory_manager_failure_is_degraded(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Memory Fail",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={},
    )
    factory = CustomAgentFactory(agent_id="custom-memory-fail", agent_profile=profile)
    factory._initialized = True

    captured_memory_manager: list[object | None] = [object()]

    async def fake_load_platform_retrieval_configs() -> tuple[object, None]:
        return (SimpleNamespace(), None)

    async def fake_create_memory_manager(*args: object, **kwargs: object) -> SimpleNamespace:
        raise RuntimeError("memory manager failed")

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        captured_memory_manager[0] = kwargs.get("memory_manager")
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(
        "app.services.agent.platform_config.load_platform_retrieval_configs",
        fake_load_platform_retrieval_configs,
    )
    monkeypatch.setattr(
        "app.core.memory.adapters.setup.create_memory_manager",
        fake_create_memory_manager,
    )
    monkeypatch.setattr(api_module, "create_skill_agent", fake_create_skill_agent)
    monkeypatch.setattr(
        "app.platform_utils.get_storage_provider",
        lambda: SimpleNamespace(),
    )

    parent = SimpleNamespace(
        llm=SimpleNamespace(),
        executor=None,
        enable_conversation_search=False,
        incognito_mode=False,
        enable_wiki=False,
        _last_context={"chat_id": "chat-memory-fail"},
    )
    config = SubagentConfig(
        display_name="Memory Fail",
        system_prompt="Degrade memory.",
        memory_isolation=MemoryIsolationPolicy.COLLABORATIVE_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_memory_manager[0] is None
