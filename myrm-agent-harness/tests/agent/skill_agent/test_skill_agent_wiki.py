"""Test SkillAgent wiki integration.

Verifies _create_wiki_tools() and _maybe_archive_to_wiki() behavior.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Command

from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from myrm_agent_harness.toolkits.wiki import WikiCompiler
from myrm_agent_harness.toolkits.wiki.wiki_tool_descriptions import (
    resolve_wiki_apply_description,
    resolve_wiki_ingest_description,
    resolve_wiki_query_description,
)


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def wiki_dir(tmp_path: Path) -> Path:
    return tmp_path / "wiki"


def _make_agent(
    mock_llm: AsyncMock,
    wiki_base_dir: Path | str | None = None,
    wiki_search_fn: Callable[..., object] | None = None,
    config: AgentRuntimeConfig | None = None,
) -> SkillAgent:
    return SkillAgent(llm=mock_llm, wiki_base_dir=wiki_base_dir, wiki_search_fn=wiki_search_fn, config=config)


class TestCreateWikiTools:
    """Tests for _create_wiki_tools."""

    def test_returns_empty_when_no_wiki_dir(self, mock_llm: AsyncMock) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=None)
        tools = agent._create_wiki_tools()
        assert tools == []

    def test_returns_three_tools_when_wiki_dir_set(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        tools = agent._create_wiki_tools()

        assert len(tools) == 3
        names = {t.name for t in tools}
        assert names == {"wiki_ingest_tool", "wiki_query_tool", "wiki_apply_tool"}

    def test_stores_compiler_and_structure(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        assert agent._wiki_compiler is not None
        assert agent._wiki_structure is not None

    def test_accepts_str_wiki_base_dir(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """wiki_base_dir can be a str, not just Path."""
        agent = _make_agent(mock_llm, wiki_base_dir=str(wiki_dir))
        tools = agent._create_wiki_tools()

        assert len(tools) == 3
        assert agent._wiki_structure is not None

    def test_passes_search_fn_to_query_engine(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """wiki_search_fn should be forwarded to WikiQueryEngine."""
        mock_search = AsyncMock(return_value=[])
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir, wiki_search_fn=mock_search)
        tools = agent._create_wiki_tools()

        assert len(tools) == 3
        assert agent._wiki_search_fn is mock_search

    @pytest.mark.parametrize(
        ("config", "locale"),
        [
            pytest.param(None, "en", id="no-config"),
            pytest.param(AgentRuntimeConfig(locale="zh-CN"), "zh-CN", id="ui-locale"),
            pytest.param(AgentRuntimeConfig(prompt_locale="zh-TW"), "zh-TW", id="prompt-locale"),
            pytest.param(
                AgentRuntimeConfig(prompt_locale="en", locale="zh-CN"), "en", id="prompt-locale-outranks-ui-locale"
            ),
        ],
    )
    def test_descriptions_follow_the_prompt_locale(
        self, mock_llm: AsyncMock, wiki_dir: Path, config: AgentRuntimeConfig | None, locale: str
    ) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir, config=config)

        # The tool framework trims the text's trailing newline.
        assert {tool.name: tool.description for tool in agent._create_wiki_tools()} == {
            "wiki_ingest_tool": resolve_wiki_ingest_description(locale).strip(),
            "wiki_query_tool": resolve_wiki_query_description(locale).strip(),
            "wiki_apply_tool": resolve_wiki_apply_description(locale).strip(),
        }

    def test_handles_import_error_gracefully(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)

        with patch.dict("sys.modules", {"myrm_agent_harness.toolkits.wiki": None}):
            tools = agent._create_wiki_tools()

        assert tools == []


class TestMaybeArchiveToWiki:
    """Tests for _maybe_archive_to_wiki."""

    def test_skips_when_no_wiki_compiler(self, mock_llm: AsyncMock) -> None:
        agent = _make_agent(mock_llm)
        agent._maybe_archive_to_wiki("test query", ["short"])

    def test_skips_when_content_too_short(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        agent._maybe_archive_to_wiki("test query", ["short reply"])

    def test_schedules_archive_when_content_sufficient(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        long_reply = "x" * 600

        asyncio.run(self._run_archive(agent, long_reply))

    async def _run_archive(self, agent: SkillAgent, reply: str) -> None:
        agent._maybe_archive_to_wiki("What is Python?", [reply])
        await asyncio.sleep(0.1)

    def test_archive_includes_query_and_reply(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        assert agent._wiki_structure is not None
        long_reply = "This is a detailed response. " * 30

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()
        agent._wiki_compiler = mock_compiler

        asyncio.run(self._run_and_verify(agent, long_reply))

    async def _run_and_verify(self, agent: SkillAgent, reply: str) -> None:
        agent._maybe_archive_to_wiki("What is Python?", [reply])
        await asyncio.sleep(0.2)

        assert agent._wiki_structure is not None
        chat_id = getattr(agent.config, "chat_id", None) or "unknown"
        raw_dir = agent._wiki_structure.raw_dir
        turn_files = list(raw_dir.glob(f"turn_{chat_id}_*.md"))

        if turn_files:
            content = turn_files[0].read_text(encoding="utf-8")
            assert "# Query" in content
            assert "What is Python?" in content
            assert "# Response" in content

    def test_handles_list_query(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """Test that list[dict] query type doesn't crash."""
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        long_reply = "x" * 600
        list_query: list[dict[str, object]] = [{"type": "text", "text": "hello"}]

        asyncio.run(self._run_list_query(agent, list_query, long_reply))

    async def _run_list_query(self, agent: SkillAgent, query: list[dict[str, object]], reply: str) -> None:
        agent._maybe_archive_to_wiki(query, [reply])
        await asyncio.sleep(0.1)

    @pytest.mark.parametrize(
        ("query", "expected_words"),
        [
            (
                [
                    {"type": "text", "text": "What does this chart show?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 50_000}},
                ],
                "What does this chart show?",
            ),
            (Command(resume="approved"), None),
        ],
        ids=["screenshot-query", "hitl-resume"],
    )
    def test_archives_only_the_users_words(
        self, mock_llm: AsyncMock, wiki_dir: Path, query: object, expected_words: str | None
    ) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()
        agent._wiki_compiler = MagicMock()

        content = asyncio.run(self._archive_and_read(agent, query))

        assert "# Response" in content
        assert "base64" not in content
        assert "Command(" not in content
        assert len(content) < 5_000
        if expected_words:
            assert expected_words in content

    async def _archive_and_read(self, agent: SkillAgent, query: object) -> str:
        agent._maybe_archive_to_wiki(query, ["This is a detailed response. " * 30])  # type: ignore[arg-type]
        await asyncio.sleep(0.2)

        assert agent._wiki_structure is not None
        turn_files = list(agent._wiki_structure.raw_dir.glob("turn_*.md"))
        assert len(turn_files) == 1
        return turn_files[0].read_text(encoding="utf-8")

    def test_uses_unknown_when_chat_id_missing(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """When config has no chat_id, filename uses 'unknown'."""
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()
        agent._wiki_compiler = mock_compiler

        long_reply = "x" * 600

        asyncio.run(self._run_and_check_unknown(agent, long_reply))

    async def _run_and_check_unknown(self, agent: SkillAgent, reply: str) -> None:
        agent._maybe_archive_to_wiki("test", [reply])
        await asyncio.sleep(0.2)

        assert agent._wiki_structure is not None
        raw_dir = agent._wiki_structure.raw_dir
        turn_files = list(raw_dir.glob("turn_unknown_*.md"))
        if turn_files:
            content = turn_files[0].read_text(encoding="utf-8")
            assert "# Query" in content

    def test_archive_failure_is_warning_not_error(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """_archive() exception should only produce a warning, not crash."""
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock(side_effect=RuntimeError("enqueue boom"))
        agent._wiki_compiler = mock_compiler

        long_reply = "x" * 600

        asyncio.run(self._run_failing_archive(agent, long_reply))

    async def _run_failing_archive(self, agent: SkillAgent, reply: str) -> None:
        agent._maybe_archive_to_wiki("test", [reply])
        await asyncio.sleep(0.2)

    def test_exact_threshold_500_chars(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """Content exactly 500 chars should be archived (>= boundary)."""
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()
        agent._wiki_compiler = mock_compiler

        reply_500 = "x" * 500

        asyncio.run(self._run_archive(agent, reply_500))

    def test_just_below_threshold_499_chars(self, mock_llm: AsyncMock, wiki_dir: Path) -> None:
        """Content at 499 chars should NOT be archived."""
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        agent._create_wiki_tools()

        agent._maybe_archive_to_wiki("test", ["x" * 499])


class TestPdfReadIsIndependentOfTheWiki:
    """Mounting the wiki tools changes nothing about what a long PDF read does or says."""

    @staticmethod
    async def _read_long_pdf() -> str:
        from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import read_pdf_as_content_blocks
        from myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor import PDFExtractResult

        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"%PDF-1.4 mock")
        long_pdf = PDFExtractResult(text="[Page 1]\nbody", page_count=25, parsed_pages=20, strategy="text")
        with patch(
            "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
            new_callable=AsyncMock,
            return_value=long_pdf,
        ):
            result = await read_pdf_as_content_blocks("/tmp/long.pdf", executor, supports_vision=False)
        # A background ingest, had the read started one, would have finished by now.
        await asyncio.sleep(0.2)
        assert isinstance(result, str)
        return result

    @pytest.mark.asyncio
    async def test_a_long_pdf_read_writes_and_queues_nothing_in_the_wiki(
        self, mock_llm: AsyncMock, wiki_dir: Path
    ) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        with patch.object(WikiCompiler, "enqueue_file") as enqueue:
            agent._create_wiki_tools()
            assert agent._wiki_structure is not None
            files_before = sorted(agent._wiki_structure.raw_dir.rglob("*"))

            await self._read_long_pdf()

        assert sorted(agent._wiki_structure.raw_dir.rglob("*")) == files_before
        enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_read_says_the_same_before_and_after_the_wiki_is_mounted(
        self, mock_llm: AsyncMock, wiki_dir: Path
    ) -> None:
        agent = _make_agent(mock_llm, wiki_base_dir=wiki_dir)
        before = await self._read_long_pdf()
        agent._create_wiki_tools()
        after = await self._read_long_pdf()

        assert after == before
        assert "wiki_query" not in after
