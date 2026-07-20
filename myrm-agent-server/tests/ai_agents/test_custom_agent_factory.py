"""Custom agent factory memory search rebinding tests."""

from types import SimpleNamespace

import pytest

from app.ai_agents.custom_agent_factory import (
    _apply_subagent_memory_search_rebind,
    _parent_chat_id,
    _parent_memory_search_flags,
    _rebind_subagent_memory_search_tool,
    _without_legacy_conversation_search_tool,
)


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
    assert getattr(tools[0], "name") == "memory_search_tool"
    assert getattr(tools[0], "marker") == "rebound"
    assert captured["manager"] is memory_manager
    policy = captured["search_policy"]
    backends = captured["search_backends"]
    assert getattr(policy, "allow_sessions") is True
    assert getattr(policy, "allow_wiki") is False
    provider = getattr(backends, "conversation_provider")
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
        assert getattr(search_policy, "allow_sessions") is False
        assert getattr(search_backends, "conversation_provider") is None
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
    search_tool = next(tool for tool in tools if getattr(tool, "name") == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "last quote", "corpus": "sessions"})

    assert "disabled" in result.lower() or "not enabled" in result.lower()


@pytest.mark.asyncio
async def test_ephemeral_agent_factory_rebinds_memory_search_tool(monkeypatch) -> None:
    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

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
    assert getattr(captured_tools[0], "name") == "memory_search_tool"
    assert getattr(captured_tools[0], "marker") == "rebound"


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
    assert getattr(tools[0], "marker") == "parent"


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
    from app.ai_agents.custom_agent_factory import EphemeralAgentFactory
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

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
