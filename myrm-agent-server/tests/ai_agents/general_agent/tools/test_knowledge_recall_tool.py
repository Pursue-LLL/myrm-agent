"""Tests for unified knowledge_recall_tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.tools.knowledge_recall_tool import create_knowledge_recall_tool


@pytest.mark.asyncio
async def test_knowledge_recall_all_corpora() -> None:
    manager = MagicMock()
    manager.search = AsyncMock(
        return_value=[
            MagicMock(memory_type=MagicMock(value="semantic"), content="User prefers dark mode"),
        ]
    )
    query_wiki = AsyncMock(return_value="Payment terms are net-30.")

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    result = await tool.ainvoke({"query": "preferences and contract terms", "corpus": "all"})

    assert "Memory" in result
    assert "dark mode" in result
    assert "Wiki" in result
    assert "net-30" in result
    manager.search.assert_awaited_once()
    query_wiki.assert_awaited_once_with("preferences and contract terms")


@pytest.mark.asyncio
async def test_knowledge_recall_wiki_only() -> None:
    manager = MagicMock()
    manager.search = AsyncMock()
    query_wiki = AsyncMock(return_value="Section 3 covers liability.")

    tool = create_knowledge_recall_tool(manager, query_wiki=query_wiki)
    result = await tool.ainvoke({"query": "liability clause", "corpus": "wiki"})

    assert "Wiki" in result
    assert "liability" in result
    assert "Memory" not in result
    manager.search.assert_not_called()
