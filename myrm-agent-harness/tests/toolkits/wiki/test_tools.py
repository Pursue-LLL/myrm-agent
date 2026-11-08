"""Tests for the Wiki agent tools: the tool set and ingestion of text, files and URLs."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.wiki import (
    WikiCompiler,
    WikiConfig,
    WikiQueryEngine,
    WikiStructure,
    create_wiki_tools,
)
from myrm_agent_harness.toolkits.wiki.source_loader import SourceLoadError

_FETCH_URL = "myrm_agent_harness.toolkits.wiki.wiki_agent_tools.fetch_url_markdown"
_GET_PARSER = "myrm_agent_harness.toolkits.file_parsers.get_parser"


def _raw_files(structure: WikiStructure) -> list[Path]:
    return [path for path in structure.raw_dir.rglob("*") if path.is_file()]


def _parser_returning(text: str) -> MagicMock:
    parser = MagicMock()
    parser.parse = AsyncMock(return_value=text)
    return parser


def test_create_wiki_tools_returns_three_tools(wiki_tools: list[BaseTool]) -> None:
    """Test that create_wiki_tools returns agent-facing tools only."""
    assert len(wiki_tools) == 3

    tool_names = [tool.name for tool in wiki_tools]
    assert "wiki_ingest_tool" in tool_names
    assert "wiki_query_tool" in tool_names
    assert "wiki_apply_tool" in tool_names


@pytest.mark.asyncio
async def test_wiki_ingest_tool(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
) -> None:
    """Test wiki_ingest tool."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")

    result = await ingest_tool.ainvoke(
        {
            "source": "This is test content for ingestion.",
            "filename": "test-ingest.md",
        }
    )

    assert "Successfully ingested" in result
    assert (wiki_structure.raw_dir / "test-ingest.md").exists()


@pytest.mark.asyncio
async def test_wiki_ingest_local_file(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
    tmp_path: Path,
) -> None:
    """Test wiki_ingest with a local file path."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")

    local_file = tmp_path / "local-doc.md"
    local_file.write_text("# Local Doc\nSome content here.", encoding="utf-8")

    result = await ingest_tool.ainvoke({"source": str(local_file)})

    assert "Successfully ingested" in result
    assert (wiki_structure.raw_dir / "local-doc.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["", "   ", "\n"])
async def test_wiki_ingest_blank_source_is_refused(
    wiki_tools: list[BaseTool], wiki_structure: WikiStructure, source: str
) -> None:
    """A blank source is not a document: nothing is written to raw/ and nothing is compiled."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")

    with patch.object(WikiCompiler, "enqueue_file") as enqueue:
        result = await ingest_tool.ainvoke({"source": source})

    assert result == "Failed to ingest document: The source is empty"
    assert _raw_files(wiki_structure) == []
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_wiki_ingest_url(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
) -> None:
    """Test wiki_ingest with URL source (covers URL branch)."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")

    with patch(_FETCH_URL, new_callable=AsyncMock, return_value="# URL Doc\n\nFetched content."):
        result = await ingest_tool.ainvoke(
            {
                "source": "https://example.com/test.md",
                "filename": "url-test.md",
            }
        )

    assert "Successfully ingested" in result
    assert (wiki_structure.raw_dir / "url-test.md").exists()


@pytest.mark.asyncio
async def test_wiki_ingest_url_without_readable_content_writes_nothing(
    wiki_tools: list[BaseTool], wiki_structure: WikiStructure
) -> None:
    """A page that could not be fetched is reported with its reason, never stored as a placeholder."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")
    reason = "No readable content could be fetched from https://example.com/gone"

    with (
        patch(_FETCH_URL, new_callable=AsyncMock, side_effect=SourceLoadError(reason)),
        patch.object(WikiCompiler, "enqueue_file") as enqueue,
    ):
        result = await ingest_tool.ainvoke({"source": "https://example.com/gone"})

    assert result == f"Failed to ingest document: {reason}"
    assert _raw_files(wiki_structure) == []
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_wiki_ingest_url_engine_failure_reports_no_internal_detail(
    wiki_tools: list[BaseTool], wiki_structure: WikiStructure
) -> None:
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")

    with patch(_FETCH_URL, new_callable=AsyncMock, side_effect=RuntimeError("browser pool exhausted")):
        result = await ingest_tool.ainvoke({"source": "https://example.com/page"})

    assert result == "Failed to ingest document"
    assert _raw_files(wiki_structure) == []


class TestIngestAutoCompile:
    """Tests for wiki_ingest auto-compilation trigger."""

    @pytest.mark.asyncio
    async def test_ingest_calls_enqueue_file(self, wiki_structure: WikiStructure, mock_llm: MagicMock) -> None:
        """Test that wiki_ingest triggers enqueue_file on the compiler."""
        config = WikiConfig()
        compiler = WikiCompiler(mock_llm, wiki_structure, config)
        query_engine = WikiQueryEngine(mock_llm, wiki_structure, config)
        tools = create_wiki_tools(compiler, query_engine, wiki_structure)

        ingest_tool = next(t for t in tools if t.name == "wiki_ingest_tool")

        with patch.object(compiler, "enqueue_file") as mock_enqueue:
            result = await ingest_tool.ainvoke({"source": "Test content for auto-compile.", "filename": "auto.md"})

        assert "Compilation queued" in result
        assert (wiki_structure.raw_dir / "auto.md").exists()
        mock_enqueue.assert_called_once()
        assert "auto.md" in str(mock_enqueue.call_args[0][0])


@pytest.mark.asyncio
async def test_wiki_ingest_local_txt_with_folder(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
    tmp_path: Path,
) -> None:
    """Local non-md files get .md suffix and optional folder_path."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")

    local_file = tmp_path / "notes.txt"
    local_file.write_text("Plain notes", encoding="utf-8")

    result = await ingest_tool.ainvoke(
        {
            "source": str(local_file),
            "folder_path": "Research/Notes",
        }
    )

    assert "Successfully ingested" in result
    # folder_path is normalized by WikiStructure._sanitize_path (lowercased); spell the
    # expected path the same way so the check also holds on case-sensitive filesystems.
    ingested = wiki_structure.raw_dir / "research" / "notes" / "notes.md"
    assert ingested.read_text(encoding="utf-8") == "Plain notes"


@pytest.mark.asyncio
async def test_wiki_ingest_binary_document(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
    tmp_path: Path,
) -> None:
    """A document a parser supports is ingested as the text the parser extracts."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    with patch(_GET_PARSER, return_value=_parser_returning("# Parsed PDF\n\nBody")):
        result = await ingest_tool.ainvoke({"source": str(pdf_path)})

    assert "Successfully ingested" in result
    assert (wiki_structure.raw_dir / "report.md").read_text(encoding="utf-8") == "# Parsed PDF\n\nBody"


@pytest.mark.asyncio
async def test_wiki_ingest_sniffed_binary_document(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
    tmp_path: Path,
) -> None:
    """An archive of a supported format is ingested as the text the parser extracts."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")
    epub_path = tmp_path / "book.epub"
    epub_path.write_bytes(b"PK\x03\x04")

    with patch(_GET_PARSER, return_value=_parser_returning("# Parsed Book\n\nChapter 1")):
        result = await ingest_tool.ainvoke({"source": str(epub_path)})

    assert "Successfully ingested" in result
    assert (wiki_structure.raw_dir / "book.md").read_text(encoding="utf-8") == "# Parsed Book\n\nChapter 1"


@pytest.mark.asyncio
async def test_wiki_ingest_unsupported_binary_file_is_refused(
    wiki_tools: list[BaseTool], wiki_structure: WikiStructure, tmp_path: Path
) -> None:
    """A binary file no parser supports is never decoded into replacement characters and compiled."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")
    program = tmp_path / "setup.exe"
    program.write_bytes(b"MZ\x90\x00" + bytes(range(256)) * 8)

    with patch.object(WikiCompiler, "enqueue_file") as enqueue:
        result = await ingest_tool.ainvoke({"source": str(program)})

    assert result == "Failed to ingest document: setup.exe is a binary file that no parser supports"
    assert _raw_files(wiki_structure) == []
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_wiki_ingest_legacy_encoded_file_is_stored_as_utf8(
    wiki_tools: list[BaseTool], wiki_structure: WikiStructure, tmp_path: Path
) -> None:
    """A GBK file is read as the text it is and stored in the knowledge base as UTF-8, not as replacement characters."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")
    notes = "知识库编译流程会先读取原始资料，再由模型提炼要点并写入对应的页面。\n如果资料的编码无法确认，系统宁可明确拒绝。\n"
    legacy = tmp_path / "legacy.log"
    legacy.write_bytes(notes.encode("gbk"))

    result = await ingest_tool.ainvoke({"source": str(legacy)})

    assert "Successfully ingested" in result
    assert (wiki_structure.raw_dir / "legacy.md").read_text(encoding="utf-8") == notes


@pytest.mark.asyncio
async def test_wiki_ingest_text_in_an_unidentifiable_encoding_is_refused(
    wiki_tools: list[BaseTool], wiki_structure: WikiStructure, tmp_path: Path
) -> None:
    """Text that cannot be read reliably is never decoded into replacement characters and compiled."""
    ingest_tool = next(tool for tool in wiki_tools if tool.name == "wiki_ingest_tool")
    legacy = tmp_path / "short.txt"
    legacy.write_bytes("你好，世界".encode("gbk"))

    with patch.object(WikiCompiler, "enqueue_file") as enqueue:
        result = await ingest_tool.ainvoke({"source": str(legacy)})

    assert result == (
        "Failed to ingest document: short.txt is not UTF-8 text and its encoding could not be identified reliably; "
        "save it as UTF-8 and ingest it again"
    )
    assert _raw_files(wiki_structure) == []
    enqueue.assert_not_called()
