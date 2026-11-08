"""Tests for archiving wiki_query answers back into raw/ without blocking the result."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.wiki import (
    WikiCompiler,
    WikiConfig,
    WikiQueryEngine,
    WikiStructure,
    create_wiki_tools,
)


@pytest.mark.asyncio
class TestArchiveQueryResult:
    """Tests for _archive_query_result helper."""

    @pytest.mark.asyncio
    async def test_archives_qa_pair_to_raw(self, wiki_structure: WikiStructure, mock_llm: MagicMock) -> None:
        """Test that _archive_query_result writes Q&A to raw/ and enqueues."""
        from myrm_agent_harness.toolkits.wiki.wiki_agent_tools import _archive_query_result

        config = WikiConfig()
        compiler = WikiCompiler(mock_llm, wiki_structure, config)

        await _archive_query_result(wiki_structure, compiler, "What is Python?", "Python is a programming language.")

        raw_files = list(wiki_structure.raw_dir.glob("query_archive_*.md"))
        assert len(raw_files) == 1
        content = raw_files[0].read_text(encoding="utf-8")
        assert "# Query" in content
        assert "What is Python?" in content
        assert "# Answer" in content
        assert "Python is a programming language." in content

    @pytest.mark.asyncio
    async def test_idempotent_same_question(self, wiki_structure: WikiStructure, mock_llm: MagicMock) -> None:
        """Test that archiving the same question twice doesn't create duplicates."""
        from myrm_agent_harness.toolkits.wiki.wiki_agent_tools import _archive_query_result

        config = WikiConfig()
        compiler = WikiCompiler(mock_llm, wiki_structure, config)

        await _archive_query_result(wiki_structure, compiler, "Repeat?", "Answer 1")
        await _archive_query_result(wiki_structure, compiler, "Repeat?", "Answer 2")

        raw_files = list(wiki_structure.raw_dir.glob("query_archive_*.md"))
        assert len(raw_files) == 1
        content = raw_files[0].read_text(encoding="utf-8")
        assert "Answer 1" in content

    @pytest.mark.asyncio
    async def test_different_questions_create_different_files(
        self, wiki_structure: WikiStructure, mock_llm: MagicMock
    ) -> None:
        """Test that different questions create separate archive files."""
        from myrm_agent_harness.toolkits.wiki.wiki_agent_tools import _archive_query_result

        config = WikiConfig()
        compiler = WikiCompiler(mock_llm, wiki_structure, config)

        await _archive_query_result(wiki_structure, compiler, "Question A", "Answer A")
        await _archive_query_result(wiki_structure, compiler, "Question B", "Answer B")

        raw_files = list(wiki_structure.raw_dir.glob("query_archive_*.md"))
        assert len(raw_files) == 2


class TestQueryArchiveNonBlocking:
    """Tests for wiki_query archive failure not blocking results."""

    @pytest.mark.asyncio
    async def test_archive_failure_still_returns_result(
        self, wiki_structure: WikiStructure, mock_llm: MagicMock
    ) -> None:
        """Test that archive failure does not prevent query result from being returned."""
        from unittest.mock import patch

        from myrm_agent_harness.toolkits.wiki.core.types import QueryResult

        config = WikiConfig()
        compiler = WikiCompiler(mock_llm, wiki_structure, config)
        query_engine = WikiQueryEngine(mock_llm, wiki_structure, config)
        tools = create_wiki_tools(compiler, query_engine, wiki_structure)

        query_tool = next(t for t in tools if t.name == "wiki_query_tool")

        (wiki_structure.concepts_dir / "test-topic.md").write_text("# Test Topic\nContent here.")

        mock_query_result = QueryResult(
            question="test?",
            answer="good answer",
            related_articles=[str(wiki_structure.concepts_dir / "test-topic.md")],
            should_archive=True,
            confidence_score=1.0,
        )

        with (
            patch.object(query_engine, "query", new=AsyncMock(return_value=mock_query_result)),
            patch(
                "myrm_agent_harness.toolkits.wiki.wiki_agent_tools._archive_query_result",
                side_effect=RuntimeError("disk full"),
            ),
        ):
            result = await query_tool.ainvoke({"question": "test?"})

        assert isinstance(result, dict)
        assert "content" in result
        assert "metadata" in result
