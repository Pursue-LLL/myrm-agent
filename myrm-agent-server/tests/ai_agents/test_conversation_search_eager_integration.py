"""Integration: GeneralAgent conversation_search eager wiring and execution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolSource
from myrm_agent_harness.toolkits.memory.conversation_search import (
    ConversationSearchHit,
    ConversationSearchRequest,
    ConversationSearchResponse,
    create_conversation_search_tool,
)


class FakeConversationSearchProvider:
    async def search(self, request: ConversationSearchRequest) -> ConversationSearchResponse:
        return ConversationSearchResponse(
            mode="search",
            query=request.query,
            hits=[
                ConversationSearchHit(
                    conversation_id="chat-integration",
                    title="Prior deployment thread",
                    snippet="We agreed on Docker Compose.",
                    summary="Deployment used local SQLite.",
                    score=0.91,
                    source="hybrid",
                )
            ],
        )


@pytest.mark.asyncio
async def test_conversation_search_eager_wiring_and_execute(monkeypatch) -> None:
    """Server wiring: tools append → registry resolve → direct tool run."""
    from app.ai_agents.general_agent.conversation_search_setup import (
        append_conversation_search_tool,
    )

    monkeypatch.setattr(
        "app.ai_agents.general_agent.conversation_search_setup.ConversationHistorySearchProvider",
        lambda **_kwargs: FakeConversationSearchProvider(),
    )

    tools: list[object] = []
    append_conversation_search_tool(
        tools,
        current_chat_id="chat-integration",
        agent_id="agent-main",
        memory_manager=SimpleNamespace(),
    )

    assert len(tools) == 1
    assert getattr(tools[0], "name", "") == "conversation_search_tool"

    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool, source=ToolSource.USER, deferred=False)

    resolved_names = {t.name for t in registry.resolve()}
    assert "conversation_search_tool" in resolved_names
    assert "conversation_search_tool" not in {t.name for t in registry.get_deferred_tools()}

    result = await tools[0].ainvoke({"query": "deployment"})
    assert "Prior deployment thread" in result
    assert "Docker Compose" in result


@pytest.mark.asyncio
async def test_conversation_search_tool_runnable_when_registered_eager() -> None:
    """Eager registration exposes tool in resolve() and executes directly."""
    tool = create_conversation_search_tool(FakeConversationSearchProvider())
    registry = ToolRegistry()
    registry.register(tool, source=ToolSource.USER, deferred=False)

    resolved_names = {t.name for t in registry.resolve()}
    assert "conversation_search_tool" in resolved_names

    output = await tool.ainvoke({"query": "deployment"})
    assert "Prior deployment thread" in output
