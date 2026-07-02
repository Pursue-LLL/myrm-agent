"""Custom agent factory conversation search wiring tests."""

from types import SimpleNamespace

from app.ai_agents.custom_agent_factory import (
    _append_scoped_conversation_search,
    _parent_chat_id,
    _without_inherited_conversation_search,
)


def test_parent_chat_id_reads_last_context_chat_id() -> None:
    parent = SimpleNamespace(_last_context={"chat_id": "chat-123", "session_id": "session-456"})

    assert _parent_chat_id(parent) == "chat-123"


def test_parent_chat_id_falls_back_to_session_id() -> None:
    parent = SimpleNamespace(_last_context={"session_id": "session-456"})

    assert _parent_chat_id(parent) == "session-456"


def test_without_inherited_conversation_search_removes_parent_tool() -> None:
    tools = [SimpleNamespace(name="conversation_search_tool"), SimpleNamespace(name="bash")]

    filtered = _without_inherited_conversation_search(tools)

    assert [tool.name for tool in filtered] == ["bash"]


def test_append_scoped_conversation_search_uses_server_provider(monkeypatch) -> None:
    class FakeMemoryManager:
        pass

    class FakeProvider:
        def __init__(self, *, current_chat_id: str | None, agent_id: str, memory_manager: object) -> None:
            self.current_chat_id = current_chat_id
            self.agent_id = agent_id
            self.memory_manager = memory_manager

    memory_manager = FakeMemoryManager()
    created: dict[str, object] = {}

    def fake_create_conversation_search_tool(provider: object) -> object:
        created["provider"] = provider
        return SimpleNamespace(name="conversation_search_tool")

    import myrm_agent_harness.toolkits.memory.conversation_search as conversation_search_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    import app.services.chat.conversation_search_service as search_service_module

    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)
    monkeypatch.setattr(search_service_module, "ConversationHistorySearchProvider", FakeProvider)
    monkeypatch.setattr(
        conversation_search_module,
        "create_conversation_search_tool",
        fake_create_conversation_search_tool,
    )

    tools: list[object] = []
    _append_scoped_conversation_search(
        tools,
        current_chat_id="chat-123",
        agent_id="agent-a",
        memory_manager=memory_manager,
    )

    assert [tool.name for tool in tools] == ["conversation_search_tool"]
    provider = created["provider"]
    assert isinstance(provider, FakeProvider)
    assert provider.current_chat_id == "chat-123"
    assert provider.agent_id == "agent-a"
    assert provider.memory_manager is memory_manager


def test_append_scoped_conversation_search_skips_when_memory_manager_none() -> None:
    tools: list[object] = [SimpleNamespace(name="bash")]

    _append_scoped_conversation_search(
        tools,
        current_chat_id="chat-123",
        agent_id="agent-a",
        memory_manager=None,
    )

    assert [tool.name for tool in tools] == ["bash"]


def test_append_scoped_conversation_search_skips_when_memory_manager_wrong_type() -> None:
    tools: list[object] = []

    _append_scoped_conversation_search(
        tools,
        current_chat_id="chat-123",
        agent_id="agent-a",
        memory_manager=object(),
    )

    assert tools == []
