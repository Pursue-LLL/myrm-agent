"""Custom agent factory memory search rebinding tests."""

import asyncio
from types import SimpleNamespace

import pytest

from app.ai_agents.custom_agent_factory import (
    _apply_subagent_memory_search_rebind,
    _build_subagent_wiki_query,
    _coerce_str_list,
    _filter_tools_by_profile,
    _parent_chat_id,
    _parent_memory_search_flags,
    _rebind_subagent_memory_search_tool,
    _without_legacy_conversation_search_tool,
)


def test_coerce_str_list_keeps_string_items_only() -> None:
    assert _coerce_str_list(["a", 1, "b"]) == ["a", "b"]
    assert _coerce_str_list("not-a-list") == []


def test_filter_tools_by_profile_respects_enabled_groups() -> None:
    tools = [
        SimpleNamespace(name="memory_search_tool"),
        SimpleNamespace(name="browser_navigate_tool"),
        SimpleNamespace(name="bash"),
    ]
    filtered = _filter_tools_by_profile(tools, ("memory",))
    assert [tool.name for tool in filtered] == ["memory_search_tool", "bash"]


def test_filter_tools_by_profile_enables_all_builtin_groups() -> None:
    tools = [
        SimpleNamespace(name="web_search_tool"),
        SimpleNamespace(name="browser_navigate_tool"),
        SimpleNamespace(name="file_read_tool"),
        SimpleNamespace(name="bash_code_execute_tool"),
        SimpleNamespace(name="computer_use_tool"),
        SimpleNamespace(name="memory_search_tool"),
        SimpleNamespace(name="kanban_list_tasks_tool"),
        SimpleNamespace(name="wiki_search_tool"),
    ]
    enabled = (
        "web_search",
        "browser",
        "file_ops",
        "code_execute",
        "computer_use",
        "memory",
        "kanban",
        "wiki",
    )
    filtered = _filter_tools_by_profile(tools, enabled)
    assert len(filtered) == len(tools)


def test_parent_chat_id_returns_none_for_invalid_context() -> None:
    assert _parent_chat_id(SimpleNamespace(_last_context="bad")) is None


def test_build_subagent_wiki_query_requires_lite_llm() -> None:
    assert _build_subagent_wiki_query(SimpleNamespace(), SimpleNamespace(), agent_id="a") is None


@pytest.mark.asyncio
async def test_build_subagent_wiki_query_returns_callable(monkeypatch) -> None:
    class FakeArchiver:
        async def query_wiki(self, question: str) -> str:
            return f"answer:{question}"

    monkeypatch.setattr(
        "app.services.wiki.vault_service.get_wiki_archiver",
        lambda *_args, **_kwargs: FakeArchiver(),
    )

    query = _build_subagent_wiki_query(
        SimpleNamespace(_lite_llm=SimpleNamespace()),
        SimpleNamespace(),
        agent_id="agent-wiki",
    )
    assert query is not None
    assert await query("pricing") == "answer:pricing"


def test_rebind_subagent_memory_search_tool_skips_non_memory_manager() -> None:
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    _rebind_subagent_memory_search_tool(
        tools,
        memory_manager=SimpleNamespace(),
        agent_id="agent-a",
        chat_id="chat-1",
        allow_sessions=True,
        allow_wiki=False,
        query_wiki=None,
    )
    assert tools[0].marker == "parent"


def test_rebind_subagent_memory_search_tool_noop_when_rebuild_missing(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    def fake_create_memory_tools(*args: object, **kwargs: object) -> list[object]:
        return [SimpleNamespace(name="memory_save_tool")]

    import myrm_agent_harness.toolkits as toolkits_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(toolkits_module, "create_memory_tools", fake_create_memory_tools)
    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)

    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    _rebind_subagent_memory_search_tool(
        tools,
        memory_manager=FakeMemoryManager(),
        agent_id="agent-a",
        chat_id="chat-1",
        allow_sessions=False,
        allow_wiki=False,
        query_wiki=None,
    )
    assert tools[0].marker == "parent"


def test_rebind_subagent_memory_search_tool_noop_when_tool_absent(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)

    tools: list[object] = [SimpleNamespace(name="bash")]
    _rebind_subagent_memory_search_tool(
        tools,
        memory_manager=FakeMemoryManager(),
        agent_id="agent-a",
        chat_id="chat-1",
        allow_sessions=False,
        allow_wiki=False,
        query_wiki=None,
    )
    assert tools[0].name == "bash"


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
        return SimpleNamespace(enabled_prebuilt_ids=["alpha-skill"])

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
        return SimpleNamespace(enabled_prebuilt_ids=["mcp-skill"])

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
        return SimpleNamespace(enabled_prebuilt_ids="not-a-list")

    monkeypatch.setattr(
        "app.core.skills.store.user_config.UserSkillConfigManager.get_config",
        fake_get_user_skill_config,
    )

    await factory._ensure_initialized()

    assert factory._initialized is True
    assert captured_kwargs["allowed_prebuilt_ids"] == frozenset()


def test_parent_chat_id_reads_last_context_chat_id() -> None:
    parent = SimpleNamespace(_last_context={"chat_id": "chat-123", "session_id": "session-456"})

    assert _parent_chat_id(parent) == "chat-123"


def test_parent_chat_id_falls_back_to_session_id() -> None:
    parent = SimpleNamespace(_last_context={"session_id": "session-456"})

    assert _parent_chat_id(parent) == "session-456"


def test_without_legacy_conversation_search_tool_removes_parent_tool() -> None:
    tools = [SimpleNamespace(name="conversation_search_tool"), SimpleNamespace(name="bash")]

    filtered = _without_legacy_conversation_search_tool(tools)

    assert [tool.name for tool in filtered] == ["bash"]


def test_parent_memory_search_flags_respects_opt_in_and_incognito() -> None:
    parent_on = SimpleNamespace(enable_conversation_search=True, incognito_mode=False, enable_wiki=True)
    parent_off = SimpleNamespace(enable_conversation_search=False, incognito_mode=False, enable_wiki=True)
    parent_incognito = SimpleNamespace(enable_conversation_search=True, incognito_mode=True, enable_wiki=True)

    assert _parent_memory_search_flags(parent_on) == (True, True)
    assert _parent_memory_search_flags(parent_off) == (False, True)
    assert _parent_memory_search_flags(parent_incognito) == (False, False)


def test_rebind_subagent_memory_search_tool_replaces_inherited_tool(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    class FakeProvider:
        def __init__(self, *, current_chat_id: str | None, agent_id: str, memory_manager: object) -> None:
            self.current_chat_id = current_chat_id
            self.agent_id = agent_id
            self.memory_manager = memory_manager

    captured: dict[str, object] = {}

    def fake_create_memory_tools(
        manager: object,
        recall_mode: object = None,
        *,
        search_policy: object = None,
        search_backends: object = None,
    ) -> list[object]:
        captured["manager"] = manager
        captured["search_policy"] = search_policy
        captured["search_backends"] = search_backends
        return [SimpleNamespace(name="memory_search_tool", marker="rebound")]

    import myrm_agent_harness.toolkits as toolkits_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    import app.services.chat.conversation_search_service as search_service_module

    monkeypatch.setattr(toolkits_module, "create_memory_tools", fake_create_memory_tools)
    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)
    monkeypatch.setattr(search_service_module, "ConversationHistorySearchProvider", FakeProvider)

    memory_manager = FakeMemoryManager()
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]

    _rebind_subagent_memory_search_tool(
        tools,
        memory_manager=memory_manager,
        agent_id="agent-a",
        chat_id="chat-123",
        allow_sessions=True,
        allow_wiki=False,
        query_wiki=None,
    )

    assert len(tools) == 1
    assert tools[0].name == "memory_search_tool"
    assert tools[0].marker == "rebound"
    assert captured["manager"] is memory_manager
    policy = captured["search_policy"]
    backends = captured["search_backends"]
    assert policy.allow_sessions is True
    assert policy.allow_wiki is False
    provider = backends.conversation_provider
    assert isinstance(provider, FakeProvider)
    assert provider.current_chat_id == "chat-123"
    assert provider.agent_id == "agent-a"


def test_rebind_subagent_memory_search_tool_skips_sessions_when_opt_in_off(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    def fake_create_memory_tools(
        manager: object,
        recall_mode: object = None,
        *,
        search_policy: object = None,
        search_backends: object = None,
    ) -> list[object]:
        assert search_policy.allow_sessions is False
        assert search_backends.conversation_provider is None
        return [SimpleNamespace(name="memory_search_tool")]

    import myrm_agent_harness.toolkits as toolkits_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(toolkits_module, "create_memory_tools", fake_create_memory_tools)
    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)

    tools: list[object] = [SimpleNamespace(name="memory_search_tool")]
    _rebind_subagent_memory_search_tool(
        tools,
        memory_manager=FakeMemoryManager(),
        agent_id="agent-a",
        chat_id="chat-123",
        allow_sessions=False,
        allow_wiki=False,
        query_wiki=None,
    )


@pytest.mark.asyncio
async def test_rebound_memory_search_tool_blocks_sessions_when_opt_in_off() -> None:
    from myrm_agent_harness.toolkits import create_memory_tools
    from myrm_agent_harness.toolkits.memory.memory_search_policy import MemorySearchPolicy

    class FakeMemoryManager:
        approval_required = False
        last_retrieval_trace = None

        async def search(self, *args: object, **kwargs: object) -> list[object]:
            return []

        @property
        def active_session(self) -> None:
            return None

    manager = FakeMemoryManager()
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=False),
    )
    search_tool = next(tool for tool in tools if tool.name == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "last quote", "corpus": "sessions"})

    assert "disabled" in result.lower() or "not enabled" in result.lower()


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_rebinds_memory_search_tool(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

    class FakeMemoryManager:
        approval_required = False

    captured_tools: list[object] = []

    def fake_create_memory_tools(
        manager: object,
        recall_mode: object = None,
        *,
        search_policy: object = None,
        search_backends: object = None,
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


def test_apply_subagent_memory_search_rebind_skips_without_memory_group() -> None:
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    rebind_calls: list[object] = []

    def _track_rebind(*args: object, **kwargs: object) -> None:
        rebind_calls.append((args, kwargs))

    import app.ai_agents.custom_agent_factory as factory_module

    original = factory_module._rebind_subagent_memory_search_tool
    factory_module._rebind_subagent_memory_search_tool = _track_rebind  # type: ignore[assignment]
    try:
        _apply_subagent_memory_search_rebind(
            tools,
            parent_agent=SimpleNamespace(),
            agent_id="researcher",
            memory_manager=SimpleNamespace(),
            enabled_builtin=("web_search",),
        )
    finally:
        factory_module._rebind_subagent_memory_search_tool = original  # type: ignore[assignment]

    assert rebind_calls == []
    assert tools[0].marker == "parent"


def test_apply_subagent_memory_search_rebind_skips_without_manager() -> None:
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    rebind_calls: list[object] = []

    def _track_rebind(*args: object, **kwargs: object) -> None:
        rebind_calls.append((args, kwargs))

    import app.ai_agents.custom_agent_factory as factory_module

    original = factory_module._rebind_subagent_memory_search_tool
    factory_module._rebind_subagent_memory_search_tool = _track_rebind  # type: ignore[assignment]
    try:
        _apply_subagent_memory_search_rebind(
            tools,
            parent_agent=SimpleNamespace(),
            agent_id="researcher",
            memory_manager=None,
            enabled_builtin=("memory",),
        )
    finally:
        factory_module._rebind_subagent_memory_search_tool = original  # type: ignore[assignment]

    assert rebind_calls == []


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_keeps_parent_tool_without_memory_group(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

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
        metadata={"personality_style": "default"},
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
async def test_ephemeral_agent_factory_fork_context_clears_system_prompt(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

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
        return SimpleNamespace(enabled_prebuilt_ids=["concurrent-skill"])

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
        return SimpleNamespace(enabled_prebuilt_ids=["safe-default"])

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


@pytest.mark.asyncio
async def test_custom_agent_factory_build_applies_personality_style(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Friendly",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={"personality_style": "friendly"},
    )
    factory = CustomAgentFactory(agent_id="custom-friendly", agent_profile=profile)
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
        _last_context={"chat_id": "chat-friendly"},
    )
    config = SubagentConfig(
        display_name="Friendly",
        system_prompt="Base prompt.",
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_spec
    system_prompt = captured_spec[0].system_prompt
    assert isinstance(system_prompt, str)
    assert "Communication Style" in system_prompt


@pytest.mark.asyncio
async def test_custom_agent_factory_build_personality_template_failure_is_non_fatal(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import MemoryIsolationPolicy, SubagentConfig

    from app.ai_agents.custom_agent_factory import CustomAgentFactory

    profile = SimpleNamespace(
        display_name="Personality Fail",
        skills=[],
        enabled_builtin_tools=(),
        max_iterations=8,
        memory_policy=None,
        metadata={"personality_style": "friendly"},
    )
    factory = CustomAgentFactory(agent_id="custom-personality-fail", agent_profile=profile)
    factory._initialized = True

    captured_spec: list[object] = []

    def fake_get_personality_template(_style: str) -> SimpleNamespace:
        raise RuntimeError("template load failed")

    async def fake_create_skill_agent(**kwargs: object) -> SimpleNamespace:
        spec = kwargs.get("spec")
        if spec is not None:
            captured_spec.append(spec)
        return SimpleNamespace()

    import myrm_agent_harness.api as api_module

    monkeypatch.setattr(
        "app.ai_agents.personality_templates.get_personality_template",
        fake_get_personality_template,
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
        _last_context={"chat_id": "chat-personality-fail"},
    )
    config = SubagentConfig(
        display_name="Personality Fail",
        system_prompt="Base prompt.",
        memory_isolation=MemoryIsolationPolicy.EPHEMERAL_SESSION,
    )

    await factory.build(config, [], "task", parent, current_depth=1)

    assert captured_spec
    assert captured_spec[0].system_prompt == "Base prompt."


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_uses_config_llm(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

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

    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

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

    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory

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
