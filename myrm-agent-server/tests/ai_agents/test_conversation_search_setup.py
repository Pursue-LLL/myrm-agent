"""GeneralAgent conversation_search opt-in wiring tests."""

from types import SimpleNamespace

from app.ai_agents.general_agent.conversation_search_setup import append_conversation_search_tool


def test_append_conversation_search_tool_registers_turn1(monkeypatch) -> None:
    class FakeMemoryManager:
        pass

    class FakeProvider:
        def __init__(self, *, current_chat_id: str | None, agent_id: str | None, memory_manager: object) -> None:
            self.current_chat_id = current_chat_id
            self.agent_id = agent_id
            self.memory_manager = memory_manager

    created: dict[str, object] = {}

    def fake_create_conversation_search_tool(provider: object) -> object:
        created["provider"] = provider
        return SimpleNamespace(name="conversation_search_tool")

    monkeypatch.setattr(
        "app.ai_agents.general_agent.conversation_search_setup.ConversationHistorySearchProvider",
        FakeProvider,
    )
    monkeypatch.setattr(
        "app.ai_agents.general_agent.conversation_search_setup.create_conversation_search_tool",
        fake_create_conversation_search_tool,
    )

    tools: list[object] = []
    memory_manager = FakeMemoryManager()

    append_conversation_search_tool(
        tools,
        current_chat_id="chat-456",
        agent_id="agent-b",
        memory_manager=memory_manager,
    )
    assert [tool.name for tool in tools] == ["conversation_search_tool"]
    provider = created["provider"]
    assert isinstance(provider, FakeProvider)
    assert provider.current_chat_id == "chat-456"
    assert provider.agent_id == "agent-b"
    assert provider.memory_manager is memory_manager
