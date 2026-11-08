"""Fixtures shared by the Wiki agent-tool tests (ingest, query, archive, path safety)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.wiki import (
    WikiCompiler,
    WikiConfig,
    WikiQueryEngine,
    WikiStructure,
    create_wiki_tools,
)


@pytest.fixture
def temp_wiki_dir(tmp_path: Path) -> Path:
    """Create temporary wiki directory."""
    wiki_dir = tmp_path / "test-wiki"
    return wiki_dir


@pytest.fixture
def wiki_structure(temp_wiki_dir: Path) -> WikiStructure:
    """Create WikiStructure instance."""
    structure = WikiStructure(temp_wiki_dir)
    structure.ensure_structure()
    return structure


@pytest.fixture
def mock_llm() -> MagicMock:
    """Create mock LLM."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def wiki_tools(
    mock_llm: MagicMock,
    wiki_structure: WikiStructure,
) -> list[BaseTool]:
    """Create agent-facing wiki tools."""
    config = WikiConfig()
    compiler = WikiCompiler(mock_llm, wiki_structure, config)
    query_engine = WikiQueryEngine(mock_llm, wiki_structure, config)
    return create_wiki_tools(compiler, query_engine, wiki_structure)
