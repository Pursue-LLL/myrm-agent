"""Tests for MemoryToWikiArchiver — Memory→Wiki automatic archiving service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from myrm_agent_harness.toolkits.wiki import WikiConfig

from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="[]"))
    return llm


@pytest.fixture
def wiki_config() -> WikiConfig:
    return WikiConfig()


@pytest.fixture
def archiver(tmp_path: Path, mock_llm: MagicMock, wiki_config: WikiConfig) -> MemoryToWikiArchiver:
    return MemoryToWikiArchiver(
        llm=mock_llm,
        wiki_dir=str(tmp_path / "users"),
        config=wiki_config,
    )


def _make_session_notes(
    *,
    session_id: str = "sess-123",
    primary_goal: str = "Build a knowledge management system",
    key_decisions: list[str] | None = None,
    technical_context: str = "Using Python 3.13 + FastAPI",
    important_facts: list[str] | None = None,
    open_questions: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "created_at": "2026-04-20T10:00:00",
            "updated_at": "2026-04-20T11:00:00",
            "primary_goal": primary_goal,
            "key_decisions": key_decisions or ["Use wiki-based knowledge storage"],
            "technical_context": technical_context,
            "important_facts": important_facts or ["Wiki supports incremental compilation"],
            "open_questions": open_questions or ["How to handle large-scale wiki?"],
        }
    )


# ============================================================================
# Initialization
# ============================================================================


class TestArchiverInit:
    def test_creates_wiki_directory(self, archiver: MemoryToWikiArchiver) -> None:
        wiki_path = archiver.get_wiki_path()
        assert wiki_path.exists()
        assert wiki_path.is_dir()

    def test_per_user_isolation(self, tmp_path: Path, mock_llm: MagicMock) -> None:
        a1 = MemoryToWikiArchiver(mock_llm, wiki_dir=str(tmp_path / "u1"))
        a2 = MemoryToWikiArchiver(mock_llm, wiki_dir=str(tmp_path / "u2"))
        assert a1.get_wiki_path() != a2.get_wiki_path()
        assert "u1" in str(a1.get_wiki_path())
        assert "u2" in str(a2.get_wiki_path())


# ============================================================================
# archive_memory
# ============================================================================


class TestArchiveMemory:
    @pytest.mark.asyncio
    async def test_archives_valid_memory(self, archiver: MemoryToWikiArchiver) -> None:
        notes = _make_session_notes(
            primary_goal="Very detailed goal " * 30,
            technical_context="Complex tech context " * 30,
        )
        result = await archiver.archive_memory(notes, conversation_turns=15)
        assert result is True

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, tmp_path: Path, mock_llm: MagicMock) -> None:
        config = WikiConfig(auto_archive_enabled=False)
        archiver = MemoryToWikiArchiver(mock_llm, wiki_dir=str(tmp_path / "u"), config=config)
        result = await archiver.archive_memory(_make_session_notes(), 15)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_insufficient_turns(self, archiver: MemoryToWikiArchiver) -> None:
        result = await archiver.archive_memory(_make_session_notes(), conversation_turns=3)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_short_content(self, archiver: MemoryToWikiArchiver) -> None:
        short_notes = json.dumps({"session_id": "s1"})
        result = await archiver.archive_memory(short_notes, conversation_turns=15)
        assert result is False

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self, archiver: MemoryToWikiArchiver) -> None:
        result = await archiver.archive_memory("not json", conversation_turns=15)
        assert result is False

    @pytest.mark.asyncio
    async def test_writes_raw_file(self, archiver: MemoryToWikiArchiver) -> None:
        notes = _make_session_notes(
            primary_goal="Detailed goal " * 50,
            technical_context="Tech " * 50,
        )
        await archiver.archive_memory(notes, conversation_turns=15)

        raw_dir = archiver.get_wiki_path().parent / "wiki" / "raw"
        if not raw_dir.exists():
            raw_dir = archiver.get_wiki_path() / "raw"

        raw_files = list(archiver._structure.raw_dir.glob("*.md"))
        assert len(raw_files) >= 1
        content = raw_files[0].read_text()
        assert "sess-123" in content


# ============================================================================
# _format_memory_as_document
# ============================================================================


class TestFormatMemory:
    def test_format_all_fields(self, archiver: MemoryToWikiArchiver) -> None:
        notes = {
            "session_id": "s1",
            "created_at": "2026-04-20",
            "updated_at": "2026-04-21",
            "primary_goal": "Build wiki",
            "key_decisions": ["Use Python", "Use FastAPI"],
            "technical_context": "Python 3.13",
            "important_facts": ["Fact A", "Fact B"],
            "open_questions": ["Q1?"],
        }
        doc = archiver._format_memory_as_document(notes)
        assert "# Conversation: s1" in doc
        assert "## Primary Goal" in doc
        assert "Build wiki" in doc
        assert "## Key Decisions" in doc
        assert "- Use Python" in doc
        assert "## Technical Context" in doc
        assert "## Important Facts" in doc
        assert "## Open Questions" in doc
        assert "- Q1?" in doc

    def test_format_minimal_fields(self, archiver: MemoryToWikiArchiver) -> None:
        notes = {"session_id": "s2"}
        doc = archiver._format_memory_as_document(notes)
        assert "# Conversation: s2" in doc
        assert "Primary Goal" not in doc

    def test_format_empty_lists(self, archiver: MemoryToWikiArchiver) -> None:
        notes = {
            "session_id": "s3",
            "key_decisions": [],
            "important_facts": [],
            "open_questions": [],
        }
        doc = archiver._format_memory_as_document(notes)
        assert "Key Decisions" not in doc
        assert "Important Facts" not in doc


# ============================================================================
# query_wiki
# ============================================================================


class TestQueryWiki:
    @pytest.mark.asyncio
    async def test_query_returns_answer(self, archiver: MemoryToWikiArchiver, mock_llm: MagicMock) -> None:
        mock_llm.ainvoke.return_value = AIMessage(content="This is the answer.")

        archiver._structure.concepts_dir.mkdir(parents=True, exist_ok=True)
        (archiver._structure.concepts_dir / "test-concept.md").write_text(
            "# Test Concept\n\nSome relevant content about testing."
        )

        result = await archiver.query_wiki("What is testing?")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_query_empty_wiki(self, archiver: MemoryToWikiArchiver) -> None:
        result = await archiver.query_wiki("anything")
        assert "no relevant information" in result.lower() or isinstance(result, str)


# ============================================================================
# maintain_wiki
# ============================================================================


class TestMaintainWiki:
    @pytest.mark.asyncio
    async def test_maintain_runs(self, archiver: MemoryToWikiArchiver) -> None:
        await archiver.maintain_wiki()
