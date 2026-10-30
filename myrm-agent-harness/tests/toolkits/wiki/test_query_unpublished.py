"""Draft and blocked pages never reach a ``WikiQueryEngine`` answer, whichever retrieval path found them."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval.query import WikiQueryEngine

_MARKER = "UNPUBLISHED-MARKER"


@pytest.fixture
def wiki_structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path)
    structure.ensure_structure()
    return structure


@pytest.fixture
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content="answer")
    return llm


def _write_page(structure: WikiStructure, name: str, publish_status: str, body: str) -> str:
    content = f"---\npublish_status: {publish_status}\n---\n## Compiled Truth\n{body}\n"
    structure.get_concept_file_path(name).write_text(content, encoding="utf-8")
    return content


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "blocked"])
async def test_keyword_fallback_skips_unpublished_pages(
    wiki_structure: WikiStructure, mock_llm: AsyncMock, status: str
) -> None:
    engine = WikiQueryEngine(llm=mock_llm, structure=wiki_structure, config=WikiConfig(enable_semantic_search=False))
    _write_page(wiki_structure, "Published Graphs", "published", "Graph traversal algorithms explained.")
    _write_page(wiki_structure, "Hidden Graphs", status, f"{_MARKER} graph traversal algorithms.")

    result = await engine.query("graph traversal algorithms")

    assert [Path(article).stem for article in result.related_articles] == ["published-graphs"]
    assert _MARKER not in result.answer
    assert all(_MARKER not in snippet.snippet for snippet in result.source_snippets)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "blocked"])
async def test_graph_expansion_skips_unpublished_linked_pages(
    wiki_structure: WikiStructure, mock_llm: AsyncMock, status: str
) -> None:
    engine = WikiQueryEngine(llm=mock_llm, structure=wiki_structure, config=WikiConfig(enable_semantic_search=True))
    hub = _write_page(wiki_structure, "Hub Zephyr", "published", "Zephyr overview, see [[Hidden Page]].")
    hidden = _write_page(wiki_structure, "Hidden Page", status, f"{_MARKER} unrelated words.")
    await engine._indexer.upsert("Hub Zephyr", hub)
    await engine._indexer.upsert("Hidden Page", hidden)
    engine._indexer.upsert_edges("Hub Zephyr", ["Hidden Page"])

    result = await engine.query("zephyr")

    assert [Path(article).stem for article in result.related_articles] == ["hub-zephyr"]
    assert _MARKER not in result.answer
    assert all(_MARKER not in snippet.snippet for snippet in result.source_snippets)


@pytest.mark.asyncio
async def test_pages_without_a_publish_status_stay_visible(wiki_structure: WikiStructure, mock_llm: AsyncMock) -> None:
    engine = WikiQueryEngine(llm=mock_llm, structure=wiki_structure, config=WikiConfig(enable_semantic_search=False))
    wiki_structure.get_concept_file_path("Legacy Page").write_text(
        "## Compiled Truth\nLegacy page about gravity.", encoding="utf-8"
    )

    result = await engine.query("gravity")

    assert [Path(article).stem for article in result.related_articles] == ["legacy-page"]
