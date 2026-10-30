"""Draft and blocked pages never reach a ``WikiQueryEngine`` answer, whichever retrieval path found them."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.toolkits.wiki.core.config import WikiCompileConfig, WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiCognitiveMapService,
    WikiMapEvent,
    WikiMapEventType,
    write_index_markdown,
)
from myrm_agent_harness.toolkits.wiki.pipeline.sidecar import build_directory_sidecars
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


@pytest.mark.asyncio
async def test_directory_sidecars_and_the_index_carry_nothing_of_a_demoted_page(
    wiki_structure: WikiStructure, mock_llm: AsyncMock
) -> None:
    _write_page(wiki_structure, "Ops/Runbook", "published", "Rollback runbook steps for deploys.")
    _write_page(wiki_structure, "Ops/Old Runbook", "draft", f"{_MARKER} rollback runbook steps for deploys.")
    sidecar_llm = AsyncMock(side_effect=RuntimeError("llm down"))
    await build_directory_sidecars(sidecar_llm, wiki_structure, WikiCompileConfig(), touched_concepts=[], indexer=None)
    write_index_markdown(wiki_structure)
    engine = WikiQueryEngine(llm=mock_llm, structure=wiki_structure, config=WikiConfig(enable_semantic_search=False))

    result = await engine.query("rollback runbook steps")

    assert "Rollback runbook steps for deploys." in result.answer
    assert _MARKER not in result.answer
    assert all(_MARKER not in snippet.snippet for snippet in result.source_snippets)


@pytest.mark.asyncio
async def test_graph_expansion_skips_a_linked_page_that_is_not_utf8(
    wiki_structure: WikiStructure, mock_llm: AsyncMock
) -> None:
    engine = WikiQueryEngine(llm=mock_llm, structure=wiki_structure, config=WikiConfig(enable_semantic_search=True))
    hub = _write_page(wiki_structure, "Hub Zephyr", "published", "Zephyr overview, see [[Latin Page]].")
    wiki_structure.get_concept_file_path("Latin Page").write_bytes("caf\u00e9".encode("latin-1"))
    await engine._indexer.upsert("Hub Zephyr", hub)
    await engine._indexer.upsert("Latin Page", "cafe")
    engine._indexer.upsert_edges("Hub Zephyr", ["Latin Page"])

    result = await engine.query("zephyr")

    assert [Path(article).stem for article in result.related_articles] == ["hub-zephyr"]


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["gravity", "zzzqqq matches nothing"])
async def test_answer_prefix_names_no_unpublished_page(
    wiki_structure: WikiStructure, mock_llm: AsyncMock, question: str
) -> None:
    _write_page(wiki_structure, "Published Gravity", "published", "Gravity pulls masses together.")
    _write_page(wiki_structure, "Hidden Gravity", "draft", f"{_MARKER} gravity.")
    WikiCognitiveMapService(wiki_structure).refresh(
        WikiMapEvent(event_type=WikiMapEventType.COMPILE, summary="Answer prefix publish gate")
    )
    engine = WikiQueryEngine(llm=mock_llm, structure=wiki_structure, config=WikiConfig(enable_semantic_search=False))

    result = await engine.query(question)

    assert "published-gravity" in result.answer
    assert "hidden-gravity" not in result.answer
    assert _MARKER not in result.answer
