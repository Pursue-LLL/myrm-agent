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


@pytest.mark.asyncio
async def test_execute_wiki_knowledge_query_resolves_shared_context_paths() -> None:
    from unittest.mock import patch

    archiver = MagicMock()
    archiver.query_wiki = AsyncMock(
        return_value=QueryResult(
            question="Search federated",
            answer="Federated answer",
            related_articles=["architecture"],
            confidence_score=0.95,
        ),
    )
    archiver._structure = MagicMock()

    with (
        patch(
            "app.services.wiki.knowledge_query_service.get_wiki_archiver",
            return_value=archiver,
        ) as mock_get_archiver,
        patch(
            "app.services.wiki.knowledge_query_service.resolve_wiki_knowledge_llm",
            new_callable=AsyncMock,
        ) as mock_resolve_llm,
    ):
        mock_llm = MagicMock()
        mock_resolve_llm.return_value = mock_llm

        res = await execute_wiki_knowledge_query(
            agent_id="test_agent",
            question="Search federated",
            shared_context_ids=["kb_ctx_1", "kb_ctx_2"],
            context_name_map={"kb_ctx_1": "Team Wiki"},
        )

        assert res.answer == "Federated answer"
        mock_get_archiver.assert_called_once()
        _, kwargs = mock_get_archiver.call_args
        assert kwargs["agent_id"] == "test_agent"
        assert len(kwargs["public_dirs"]) == 2
        assert kwargs["public_dir_labels"].get("kb_ctx_1") == "Team Wiki"
