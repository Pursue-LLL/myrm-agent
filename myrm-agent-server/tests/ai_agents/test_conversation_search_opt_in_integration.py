"""Integration: memory_search_tool sessions corpus opt-in and execution."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits import create_memory_tools
from myrm_agent_harness.toolkits.memory.conversation_search import (
    ConversationSearchHit,
    ConversationSearchRequest,
    ConversationSearchResponse,
)
from myrm_agent_harness.toolkits.memory.memory_search_policy import (
    MemorySearchBackends,
    MemorySearchPolicy,
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


class FakeMemoryManager:
    approval_required = False
    last_retrieval_trace = None

    async def search(self, *args: object, **kwargs: object) -> list[object]:
        return []

    @property
    def active_session(self) -> None:
        return None


@pytest.mark.asyncio
async def test_memory_search_sessions_corpus_executes_when_opt_in_on() -> None:
    manager = FakeMemoryManager()
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=True),
        search_backends=MemorySearchBackends(conversation_provider=FakeConversationSearchProvider()),
    )
    search_tool = next(tool for tool in tools if getattr(tool, "name") == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "deployment", "corpus": "sessions"})

    assert "Prior deployment thread" in result
    assert "Docker Compose" in result


@pytest.mark.asyncio
async def test_memory_search_sessions_corpus_rejected_when_opt_in_off() -> None:
    manager = FakeMemoryManager()
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=False),
    )
    search_tool = next(tool for tool in tools if getattr(tool, "name") == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "deployment", "corpus": "sessions"})

    assert "disabled" in result.lower() or "not enabled" in result.lower()
