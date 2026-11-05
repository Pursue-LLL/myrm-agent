"""Coverage gaps for agent_surface move and root facade re-exports."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface import (
    memory_recall_formatting as surface_formatting,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import (
    search_memory_corpus,
)
from myrm_agent_harness.toolkits.memory.agent_surface.wiki_memory_boundary import (
    looks_like_wiki_document,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory


def test_surface_sanitize_recalled_content_preserves_plain_text() -> None:
    assert surface_formatting.sanitize_recalled_content("hello world") == "hello world"


def test_looks_like_wiki_document_rejects_empty_content() -> None:
    assert looks_like_wiki_document("   ") is False


def test_search_description_scope_joiners_edge_cases() -> None:
    from myrm_agent_harness.toolkits.memory.agent_surface._memory_search_description import _join_en, _join_zh

    assert _join_en([]) == ""
    assert _join_en(["memory"]) == "memory"
    assert _join_en(["memory", "wiki"]) == "memory and wiki"
    assert _join_en(["memory", "wiki", "web"]) == "memory, wiki, and web"
    assert _join_zh(["长期记忆"]) == "长期记忆"
    assert _join_zh(["长期记忆", "Wiki"]) == "长期记忆与Wiki"
    assert _join_zh(["长期记忆", "Wiki", "历史会话"]) == "长期记忆、Wiki与历史会话"


@pytest.mark.asyncio
async def test_search_memory_corpus_includes_active_session_buffer() -> None:
    buffered = SemanticMemory(content="buffered session fact about Python")
    session = MagicMock()
    session.buffer_size = 1
    session.search_buffer.return_value = [buffered]

    manager = AsyncMock()
    manager.search = AsyncMock(return_value=[])
    manager.active_session = session
    manager.last_retrieval_trace = None
    manager.set_last_cited_memory_ids = MagicMock()

    with patch(
        "myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution.emit_cited_memory_ids",
        AsyncMock(),
    ):
        result = await search_memory_corpus(
            manager,
            query="Python",
            category_to_type={"knowledge": MemoryType.SEMANTIC},
            categories=None,
            limit=5,
            since=None,
            until=None,
        )

    assert "[buffered]" in result
    assert "buffered session fact" in result
    session.search_buffer.assert_called_once_with("Python")


@pytest.mark.asyncio
async def test_search_memory_corpus_empty_results_emit_retrieval_trace() -> None:
    from datetime import UTC, datetime

    from myrm_agent_harness.toolkits.memory.observability import MemoryRetrievalTrace

    manager = AsyncMock()
    manager.search = AsyncMock(return_value=[])
    manager.active_session = None
    manager.last_retrieval_trace = MemoryRetrievalTrace(
        id="trace-1",
        query_preview="missing",
        occurred_at=datetime.now(UTC),
        degraded=False,
    )
    manager.set_last_cited_memory_ids = MagicMock()

    with patch(
        "myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution.emit_cited_memory_ids",
        AsyncMock(),
    ) as emit_mock:
        result = await search_memory_corpus(
            manager,
            query="missing",
            category_to_type={"knowledge": MemoryType.SEMANTIC},
            categories=None,
            limit=5,
            since=None,
            until=None,
        )

    assert result == "No relevant memories found."
    emit_mock.assert_awaited_once()
