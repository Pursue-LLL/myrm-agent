"""Integration: memory_search_tool sessions corpus opt-in and execution."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits import create_memory_tools
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchBackends,
    MemorySearchPolicy,
)
from myrm_agent_harness.toolkits.memory.conversation_search import (
    ConversationSearchHit,
    ConversationSearchRequest,
    ConversationSearchResponse,
)


class FakeConversationSearchProvider:
    async def search(
        self, request: ConversationSearchRequest
    ) -> ConversationSearchResponse:
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
        search_backends=MemorySearchBackends(
            conversation_provider=FakeConversationSearchProvider()
        ),
    )
    search_tool = next(tool for tool in tools if tool.name == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "deployment", "corpus": "sessions"})

    text = result["content"] if isinstance(result, dict) else str(result)
    assert "Prior deployment thread" in text
    assert "Docker Compose" in text


@pytest.mark.asyncio
async def test_memory_search_sessions_corpus_with_coverage_notice_when_partial() -> (
    None
):
    from myrm_agent_harness.toolkits.memory.conversation_search.types import (
        ConversationIndexCoverage,
    )

    class PartialCoverageProvider:
        async def search(
            self, request: ConversationSearchRequest
        ) -> ConversationSearchResponse:
            return ConversationSearchResponse(
                mode="search",
                query=request.query,
                hits=[
                    ConversationSearchHit(
                        conversation_id="chat-partial",
                        title="Deployment plan",
                        snippet="Postgres cluster",
                        summary="Discussed Postgres cluster.",
                        score=0.88,
                        source="conversation_index",
                    )
                ],
                coverage=ConversationIndexCoverage(
                    total_conversations=50,
                    indexed_conversations=20,
                    coverage_ratio=0.40,
                    unindexed_recent_count=30,
                    indexing_degraded=False,
                ),
            )

    manager = FakeMemoryManager()
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=True),
        search_backends=MemorySearchBackends(
            conversation_provider=PartialCoverageProvider()
        ),
    )
    search_tool = next(tool for tool in tools if tool.name == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "Postgres", "corpus": "sessions"})
    text = result["content"] if isinstance(result, dict) else str(result)
    assert "Notice: Conversation search covered 20/50 sessions (40.0%)" in text
    assert "30 sessions pending index" in text
    assert "Deployment plan" in text


@pytest.mark.asyncio
async def test_memory_search_sessions_corpus_rejected_when_opt_in_off() -> None:
    manager = FakeMemoryManager()
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=False),
    )
    search_tool = next(tool for tool in tools if tool.name == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "deployment", "corpus": "sessions"})

    assert "disabled" in result.lower() or "not enabled" in result.lower()


@pytest.mark.asyncio
async def test_memory_search_sessions_corpus_expand_window_and_preserves_large_content() -> (
    None
):
    captured_requests: list[ConversationSearchRequest] = []
    long_expanded_text = "Step " + ("y" * 2200) + " end of expanded block"

    class LargeExpandProvider:
        async def search(
            self, request: ConversationSearchRequest
        ) -> ConversationSearchResponse:
            captured_requests.append(request)
            return ConversationSearchResponse(
                mode="search",
                query="",
                hits=[
                    ConversationSearchHit(
                        conversation_id="chat-large-expand",
                        title="Architecture Review",
                        snippet=long_expanded_text,
                        summary=None,
                        score=1.0,
                        source="conversation_index",
                        message_id="msg-target",
                    )
                ],
            )

    manager = FakeMemoryManager()
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=True),
        search_backends=MemorySearchBackends(
            conversation_provider=LargeExpandProvider()
        ),
    )
    search_tool = next(tool for tool in tools if tool.name == "memory_search_tool")

    result = await search_tool.ainvoke(
        {
            "query": "",
            "corpus": "sessions",
            "expand_conversation_id": "chat-large-expand",
            "expand_message_id": "msg-target",
            "expand_window": 6,
        }
    )

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.expand_conversation_id == "chat-large-expand"
    assert req.expand_message_id == "msg-target"
    assert req.expand_window == 6

    text = result["content"] if isinstance(result, dict) else str(result)
    assert "end of expanded block" in text
    assert len(text) > 2000
    assert "tip: pass expand_conversation_id=" not in text
