"""Tests for wiki_ingest path safety: file names and folder paths cannot leave raw/."""

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.wiki import (
    WikiStructure,
)


class TestIngestPathTraversalDefense:
    """Real end-to-end path traversal defense: no mock on path security."""

    @pytest.mark.asyncio
    async def test_traversal_filename_stripped_by_tool(
        self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure
    ) -> None:
        """Malicious filename with ../ is stripped to just the leaf name."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Payload content", "filename": "../../../etc/cron.d/evil.md"})
        assert "Successfully ingested" in result
        assert (wiki_structure.raw_dir / "evil.md").exists()
        assert not (wiki_structure.raw_dir.parent / "etc").exists()

    @pytest.mark.asyncio
    async def test_absolute_path_filename_stripped(
        self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure
    ) -> None:
        """Absolute path in filename is stripped to leaf name."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Payload", "filename": "/tmp/hacked.md"})
        assert "Successfully ingested" in result
        assert (wiki_structure.raw_dir / "hacked.md").exists()

    @pytest.mark.asyncio
    async def test_traversal_with_folder_path(self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure) -> None:
        """Traversal in filename combined with folder_path is still safe."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke(
            {
                "source": "Content",
                "filename": "../../passwd.md",
                "folder_path": "Research/AI",
            }
        )
        assert "Successfully ingested" in result
        assert (wiki_structure.raw_dir / "research" / "ai" / "passwd.md").exists()

    @pytest.mark.asyncio
    async def test_normal_ingest_still_works(self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure) -> None:
        """Normal filenames still work correctly after security hardening."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Normal doc", "filename": "my-notes.md"})
        assert "Successfully ingested" in result
        assert (wiki_structure.raw_dir / "my-notes.md").exists()
        content = (wiki_structure.raw_dir / "my-notes.md").read_text()
        assert content == "Normal doc"

    @pytest.mark.asyncio
    async def test_backslash_traversal(self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure) -> None:
        """Windows-style backslash traversal is rejected before write."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Content", "filename": "..\\..\\evil.md"})
        assert "Failed to ingest document" in result
        assert ".." in result
        assert not (wiki_structure.raw_dir.parent.parent / "evil.md").exists()

    @pytest.mark.asyncio
    async def test_empty_filename_auto_generated(
        self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure
    ) -> None:
        """Empty filename triggers auto-generated hash name, safely."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Auto-named content", "filename": ""})
        assert "Successfully ingested" in result
        raw_files = list(wiki_structure.raw_dir.glob("text_*.md"))
        assert len(raw_files) >= 1

    @pytest.mark.asyncio
    async def test_filename_with_special_chars(self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure) -> None:
        """Filenames with spaces/special chars are preserved (no traversal)."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Content", "filename": "my document (v2).md"})
        assert "Successfully ingested" in result
        assert (wiki_structure.raw_dir / "my document (v2).md").exists()

    @pytest.mark.asyncio
    async def test_folder_path_traversal_sanitized(
        self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure
    ) -> None:
        """Traversal in folder_path is sanitized by _sanitize_path."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke(
            {
                "source": "Content",
                "filename": "safe.md",
                "folder_path": "../../../etc",
            }
        )
        assert "Successfully ingested" in result
        assert not (wiki_structure.raw_dir.parent / "etc" / "safe.md").exists()

    @pytest.mark.asyncio
    async def test_double_dot_without_slash_accepted(
        self, wiki_tools: list[BaseTool], wiki_structure: WikiStructure
    ) -> None:
        """Filename '..evil.md' (no slash) is a valid name, not traversal."""
        ingest_tool = next(t for t in wiki_tools if t.name == "wiki_ingest_tool")
        result = await ingest_tool.ainvoke({"source": "Content", "filename": "..evil.md"})
        assert "Successfully ingested" in result
        assert (wiki_structure.raw_dir / "..evil.md").exists()
