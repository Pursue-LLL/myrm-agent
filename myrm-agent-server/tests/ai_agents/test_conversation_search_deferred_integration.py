"""Integration: GeneralAgent conversation_search deferred → discover → mount → execute."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
    create_discover_capability_tool,
)
from myrm_agent_harness.agent.middlewares.deferred_tool_middleware import (
    DeferredToolMiddleware,
)
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
async def test_conversation_search_deferred_discover_mount_execute(monkeypatch) -> None:
    """Server wiring: deferred_tools append → registry → discover → middleware → tool run."""
    from app.ai_agents.general_agent.conversation_search_setup import (
        append_conversation_search_tool,
    )

    monkeypatch.setattr(
        "app.ai_agents.general_agent.conversation_search_setup.ConversationHistorySearchProvider",
        lambda **_kwargs: FakeConversationSearchProvider(),
    )

    eager_tools: list[object] = []
    deferred_tools: list[object] = []
    append_conversation_search_tool(
        deferred_tools,
        current_chat_id="chat-integration",
        agent_id="agent-main",
        memory_manager=SimpleNamespace(),
    )

    assert eager_tools == []
    assert len(deferred_tools) == 1
    assert getattr(deferred_tools[0], "name", "") == "conversation_search_tool"

    registry = ToolRegistry()
    for tool in deferred_tools:
        registry.register(tool, source=ToolSource.USER, deferred=True)

    discover = create_discover_capability_tool(registry=registry)
    discover_output = await discover.ainvoke({"query": "conversation", "mode": "regex"})
    assert "conversation_search_tool" in discover_output
    assert "<AutoMountTools>" in discover_output

    middleware = DeferredToolMiddleware(registry)
    request = MagicMock()
    request.messages = [
        ToolMessage(
            content=discover_output,
            name="discover_capability_tool",
            tool_call_id="discover-1",
        )
    ]
    request.tools = []

    async def next_call(_req: object) -> str:
        return "model-response"

    await middleware.awrap_model_call(request, next_call)

    mounted = [t for t in request.tools if getattr(t, "name", "") == "conversation_search_tool"]
    assert len(mounted) == 1

    result = await mounted[0].ainvoke({"query": "deployment"})
    assert "Prior deployment thread" in result
    assert "Docker Compose" in result


@pytest.mark.asyncio
async def test_conversation_search_tool_still_runnable_when_registered_deferred_only() -> None:
    """Deferred registration does not break direct tool execution."""
    tool = create_conversation_search_tool(FakeConversationSearchProvider())
    registry = ToolRegistry()
    registry.register(tool, source=ToolSource.USER, deferred=True)

    deferred_names = {t.name for t in registry.get_deferred_tools()}
    assert "conversation_search_tool" in deferred_names

    resolved_names = {t.name for t in registry.resolve()}
    assert "conversation_search_tool" not in resolved_names

    output = await tool.ainvoke({"query": "deployment"})
    assert "Prior deployment thread" in output


@pytest.mark.asyncio
async def test_discover_lists_conversation_search_for_model_and_regex_mounts() -> None:
    """Discover schema lists deferred tool names; regex search mounts conversation_search (BM25 may score below threshold)."""
    tool = create_conversation_search_tool(FakeConversationSearchProvider())
    registry = ToolRegistry()
    registry.register(tool, source=ToolSource.USER, deferred=True)

    discover = create_discover_capability_tool(registry=registry)
    assert "conversation_search_tool" in (discover.description or "")

    result = await discover.ainvoke({"query": "conversation", "mode": "regex"})
    assert "conversation_search_tool" in result
    assert "<AutoMountTools>" in result


@pytest.mark.asyncio
async def test_discover_bm25_may_miss_conversation_search_for_natural_language() -> None:
    """BM25 on vague NL query may return empty; model still sees tool in discover description footer."""
    tool = create_conversation_search_tool(FakeConversationSearchProvider())
    registry = ToolRegistry()
    registry.register(tool, source=ToolSource.USER, deferred=True)

    discover = create_discover_capability_tool(registry=registry)
    assert "conversation_search_tool" in (discover.description or "")

    result = await discover.ainvoke({"query": "what did we discuss in the previous chat session"})
    assert "<AutoMountTools>" not in result
