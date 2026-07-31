"""Tests for wiki knowledge query SSOT."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.wiki.core.types import QueryResult

from app.services.wiki.knowledge_query_service import execute_wiki_knowledge_query


@pytest.mark.asyncio
async def test_execute_wiki_knowledge_query_reuses_injected_archiver() -> None:
    archiver = MagicMock()
    archiver.query_wiki = AsyncMock(
        return_value=QueryResult(
            question="How many plans?",
            answer="Two plans.",
            related_articles=["api"],
            confidence_score=0.9,
        ),
    )
    archiver._structure = MagicMock()

    result = await execute_wiki_knowledge_query(
        agent_id="default",
        question="How many plans?",
        archiver=archiver,
    )

    archiver.query_wiki.assert_awaited_once_with("How many plans?", query_mode="auto")
    assert result.answer == "Two plans."
    assert result.confidence_score == 0.9


@pytest.mark.asyncio
async def test_execute_wiki_knowledge_query_empty_answer_fallback() -> None:
    archiver = MagicMock()
    archiver.query_wiki = AsyncMock(
        return_value=QueryResult(
            question="missing",
            answer="",
            related_articles=[],
        ),
    )
    archiver._structure = MagicMock()

    result = await execute_wiki_knowledge_query(
        agent_id="default",
        question="missing",
        archiver=archiver,
    )

    assert result.answer == "No relevant wiki content found."
