"""Refusal-gate contract tests for the wiki knowledge query service.

Refused queries surface the refusal answer with sources cleared; answered
queries keep the engine answer and citation sources. Mirrors the REST
`refused` contract (POST /wiki/query) at the service SSOT boundary.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from myrm_agent_harness.toolkits.wiki.core.types import QueryResult

from app.services.wiki.knowledge_query_service import execute_wiki_knowledge_query
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="[]"))
    return llm


def _archiver(mock_llm: MagicMock, tmp_path: Path, result: QueryResult) -> MemoryToWikiArchiver:
    archiver = MemoryToWikiArchiver(
        llm=mock_llm,
        wiki_dir=tmp_path / "primary_wiki",
    )
    archiver.query_wiki = AsyncMock(return_value=result)
    return archiver


@pytest.mark.asyncio
async def test_refused_query_returns_refusal_answer_and_clears_sources(
    tmp_path: Path, mock_llm: MagicMock
) -> None:
    result = QueryResult(
        question="homelab nginx port",
        answer="No relevant information found in wiki. Consider ingesting more documents.",
        related_articles=[],
        confidence_score=0.0,
        refused=True,
        source_snippets=[],
    )
    query_result = await execute_wiki_knowledge_query(
        agent_id=None,
        question="homelab nginx port",
        archiver=_archiver(mock_llm, tmp_path, result),
    )

    assert query_result.refused is True
    assert "no verified basis" in query_result.answer
    assert query_result.sources == []
    assert query_result.confidence_score == 0.0


@pytest.mark.asyncio
async def test_answered_query_keeps_answer_and_sources(
    tmp_path: Path, mock_llm: MagicMock
) -> None:
    result = QueryResult(
        question="gravity mass",
        answer="Gravity attracts mass.",
        related_articles=["Gravity"],
        confidence_score=0.92,
        refused=False,
        source_snippets=[],
    )
    query_result = await execute_wiki_knowledge_query(
        agent_id=None,
        question="gravity mass",
        archiver=_archiver(mock_llm, tmp_path, result),
    )

    assert query_result.refused is False
    assert query_result.answer == "Gravity attracts mass."
    assert query_result.confidence_score == 0.92
