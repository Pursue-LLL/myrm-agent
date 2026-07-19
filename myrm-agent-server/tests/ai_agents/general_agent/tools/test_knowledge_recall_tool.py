"""Tests for unified knowledge_recall_tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.types import ClaimMemory, MemorySearchResult, MemoryType, SemanticMemory

from app.ai_agents.general_agent.tools.knowledge_recall_tool import create_knowledge_recall_tool


def _memory_result(content: str, memory_id: str = "mem-1") -> MagicMock:
    memory = MagicMock()
    memory.id = memory_id
    memory.content = content
    memory.created_at = datetime.now(UTC)
    memory.scope.channel_id = "web_chat"
    memory.source_error = None
    memory.metadata = {}
    result = MagicMock()
    result.memory = memory
    result.memory_type = MemoryType.SEMANTIC
    result.content = content
    result.score = 0.91
    return result


def _semantic_search_result(
    content: str,
    *,
    memory_id: str = "sem-1",
    source_error: str | None = None,
    created_at: datetime | None = None,
) -> MemorySearchResult:
    memory = SemanticMemory(
        content=content,
        id=memory_id,
        created_at=created_at or datetime.now(UTC),
        source_error=source_error,
    )
    return MemorySearchResult(
        memory=memory,
        memory_type=MemoryType.SEMANTIC,
        content=content,
        score=0.88,
    )


def _claim_search_result(content: str) -> MemorySearchResult:
    memory = ClaimMemory(
        content=content,
        id="claim-1",
        claim_key="key-1",
        title="Title",
        claim_text=content,
        metadata={"latest_relationship_type": "supports"},
    )
    return MemorySearchResult(
        memory=memory,
        memory_type=MemoryType.CLAIM,
        content=content,
        score=0.77,
    )


@pytest.mark.asyncio
async def test_knowledge_recall_all_corpora() -> None:
    manager = MagicMock()
    manager.search = AsyncMock(return_value=[_memory_result("User prefers dark mode")])
    manager.active_session = None
    manager.last_retrieval_trace = None
    manager.set_last_cited_memory_ids = MagicMock()
    query_wiki = AsyncMock(return_value="Payment terms are net-30.")

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    with patch(
        "app.ai_agents.general_agent.tools.knowledge_recall_tool.emit_cited_memory_ids",
        new_callable=AsyncMock,
    ) as emit_citations:
        result = await tool.ainvoke({"query": "preferences and contract terms", "corpus": "all"})

    assert "Memory" in result
    assert "dark mode" in result
    assert "Wiki" in result
    assert "net-30" in result
    manager.search.assert_awaited_once()
    query_wiki.assert_awaited_once_with("preferences and contract terms")
    emit_citations.assert_awaited()
    assert emit_citations.await_args.kwargs["tool_name"] == "knowledge_recall_tool"


@pytest.mark.asyncio
async def test_knowledge_recall_wiki_only() -> None:
    manager = MagicMock()
    manager.search = AsyncMock()
    query_wiki = AsyncMock(return_value="Section 3 covers liability.")

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    with patch(
        "app.ai_agents.general_agent.tools.knowledge_recall_tool.emit_cited_memory_ids",
        new_callable=AsyncMock,
    ) as emit_citations:
        result = await tool.ainvoke({"query": "liability clause", "corpus": "wiki"})

    assert "Wiki" in result
    assert "liability" in result
    assert "Memory" not in result
    manager.search.assert_not_called()
    emit_citations.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_recall_memory_only_empty_with_trace() -> None:
    manager = MagicMock()
    manager.search = AsyncMock(return_value=[])
    manager.active_session = None
    manager.last_retrieval_trace = {"path": "vector"}
    manager.set_last_cited_memory_ids = MagicMock()
    query_wiki = AsyncMock()

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    with patch(
        "app.ai_agents.general_agent.tools.knowledge_recall_tool.emit_cited_memory_ids",
        new_callable=AsyncMock,
    ) as emit_citations:
        result = await tool.ainvoke({"query": "missing topic", "corpus": "memory"})

    assert "No relevant memories found." in result
    emit_citations.assert_awaited_once()
    query_wiki.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_recall_includes_buffered_session_hits() -> None:
    buffered = MagicMock()
    buffered.content = "Buffered note about rollout"
    session = MagicMock()
    session.buffer_size = 1
    session.search_buffer.return_value = [buffered]

    manager = MagicMock()
    manager.search = AsyncMock(return_value=[])
    manager.active_session = session
    manager.last_retrieval_trace = None
    manager.set_last_cited_memory_ids = MagicMock()
    query_wiki = AsyncMock()

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    with patch(
        "app.ai_agents.general_agent.tools.knowledge_recall_tool.emit_cited_memory_ids",
        new_callable=AsyncMock,
    ):
        result = await tool.ainvoke({"query": "rollout", "corpus": "memory"})

    assert "[buffered]" in result
    assert "Buffered note about rollout" in result


@pytest.mark.asyncio
async def test_knowledge_recall_formats_claim_and_semantic_warnings() -> None:
    stale_path_memory = _semantic_search_result(
        "Edit src/app/main.py before deploy",
        memory_id="sem-stale",
        created_at=datetime.now(UTC) - timedelta(days=400),
    )
    source_error_memory = _semantic_search_result(
        "Broken import path",
        memory_id="sem-error",
        source_error="file missing",
    )
    claim_result = _claim_search_result("Paris is capital")

    manager = MagicMock()
    manager.search = AsyncMock(return_value=[claim_result, source_error_memory, stale_path_memory])
    manager.active_session = None
    manager.last_retrieval_trace = None
    manager.set_last_cited_memory_ids = MagicMock()
    query_wiki = AsyncMock()

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    with (
        patch(
            "app.ai_agents.general_agent.tools.knowledge_recall_tool.emit_cited_memory_ids",
            new_callable=AsyncMock,
        ),
        patch(
            "app.ai_agents.general_agent.tools.knowledge_recall_tool._is_stale",
            side_effect=lambda created_at: created_at == stale_path_memory.memory.created_at,
        ),
    ):
        result = await tool.ainvoke({"query": "facts", "corpus": "memory"})

    assert "relation=supports" in result
    assert "avoid: file missing" in result
    assert "CRITICAL: Outdated memory referencing potential paths" in result
    assert "verify before citing" not in result
    assert "Note: Before acting on recalled memories" in result


@pytest.mark.asyncio
async def test_knowledge_recall_truncates_when_budget_exceeded() -> None:
    huge = "x" * 5000
    results = [_semantic_search_result(huge, memory_id=f"mem-{idx}") for idx in range(8)]

    manager = MagicMock()
    manager.search = AsyncMock(return_value=results)
    manager.active_session = None
    manager.last_retrieval_trace = None
    manager.set_last_cited_memory_ids = MagicMock()
    query_wiki = AsyncMock()

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    with patch(
        "app.ai_agents.general_agent.tools.knowledge_recall_tool.emit_cited_memory_ids",
        new_callable=AsyncMock,
    ):
        result = await tool.ainvoke({"query": "big recall", "corpus": "memory", "limit": 8})

    assert "[recall_budget]" in result

