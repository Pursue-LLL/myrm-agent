"""Tests for the wiki_query tool: answers, refusal, citations and source metadata."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.wiki import (
    WikiCompiler,
    WikiQueryEngine,
    WikiStructure,
    create_wiki_tools,
)

# (tools, mocked compiler, mocked query engine)
DirectMockTools = tuple[list[BaseTool], MagicMock, MagicMock]


@pytest.mark.asyncio
async def test_wiki_query_tool(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
    mock_llm: MagicMock,
) -> None:
    """Test wiki_query tool."""
    query_tool = next(tool for tool in wiki_tools if tool.name == "wiki_query_tool")

    (wiki_structure.concepts_dir / "test-concept.md").write_text("# Test Concept\n\nTest content")

    mock_llm.ainvoke.return_value = AIMessage(content="This is the answer to the question.")

    result = await query_tool.ainvoke({"question": "What is Test Concept?"})

    assert isinstance(result, dict)
    assert "<<<UNTRUSTED_DATA" in result["content"]
    assert "Test Concept" in result["content"]
    assert "metadata" in result
    assert result["metadata"]["sources"][0]["filename"] == "test-concept"


@pytest.mark.asyncio
async def test_wiki_query_with_related_articles(
    wiki_tools: list[BaseTool],
    wiki_structure: WikiStructure,
    mock_llm: MagicMock,
) -> None:
    """Test wiki_query returns related articles and archive status."""
    query_tool = next(tool for tool in wiki_tools if tool.name == "wiki_query_tool")

    (wiki_structure.concepts_dir / "concept-a.md").write_text("# Concept A\nContent A")
    (wiki_structure.concepts_dir / "concept-b.md").write_text("# Concept B\nContent B")

    mock_llm.ainvoke.return_value = AIMessage(content="Detailed answer about concepts.")

    result = await query_tool.ainvoke({"question": "Tell me about Concept A and B"})

    assert isinstance(result, dict)
    assert "<<<UNTRUSTED_DATA" in result["content"]
    assert "metadata" in result
    assert len(result["metadata"]["sources"]) == 2


@pytest.mark.asyncio
async def test_wiki_query_no_articles(
    wiki_tools: list[BaseTool],
    mock_llm: MagicMock,
) -> None:
    """Test wiki_query hard refusal when no articles exist (no hallucination path)."""
    query_tool = next(tool for tool in wiki_tools if tool.name == "wiki_query_tool")

    result = await query_tool.ainvoke({"question": "What is this?"})

    assert "REFUSED" in result
    assert "no verified basis" in result


@pytest.fixture
def direct_mock_tools(wiki_structure: WikiStructure) -> DirectMockTools:
    """Create tools with directly mocked compiler/query for error path testing."""
    mock_compiler = MagicMock(spec=WikiCompiler)
    mock_query_engine = MagicMock(spec=WikiQueryEngine)

    tools = create_wiki_tools(mock_compiler, mock_query_engine, wiki_structure)
    return tools, mock_compiler, mock_query_engine


@pytest.mark.asyncio
async def test_wiki_query_exception_at_tools_layer(direct_mock_tools: DirectMockTools) -> None:
    """Test wiki_query error path when query_engine.query raises."""
    tools, _, mock_qe = direct_mock_tools
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")

    mock_qe.query = AsyncMock(side_effect=RuntimeError("query crash"))

    result = await query_tool.ainvoke({"question": "test?"})

    assert "failed" in result.lower()


@pytest.mark.asyncio
async def test_wiki_query_with_should_archive(direct_mock_tools: DirectMockTools) -> None:
    """Test wiki_query when result has should_archive=True."""
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult

    tools, _, mock_qe = direct_mock_tools
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")

    mock_qe.query = AsyncMock(
        return_value=QueryResult(
            question="test",
            answer="Great answer",
            related_articles=["concept-a", "concept-b"],
            should_archive=True,
        )
    )

    result = await query_tool.ainvoke({"question": "test"})

    assert isinstance(result, dict)
    assert "metadata" in result
    assert result["metadata"]["sources"][0]["filename"] == "concept-a"
    assert result["metadata"]["sources"][1]["filename"] == "concept-b"


@pytest.mark.asyncio
async def test_wiki_query_includes_sidecar_sources(direct_mock_tools: DirectMockTools) -> None:
    """wiki_query emits directory sidecar citations alongside article citations."""
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

    tools, _, mock_qe = direct_mock_tools
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")

    mock_qe.query = AsyncMock(
        return_value=QueryResult(
            question="test",
            answer="Layered wiki answer",
            related_articles=["/tmp/wiki/concept-a.md"],
            confidence_score=0.9,
            source_snippets=[
                SourceSnippet(
                    article_path="domain/.abstract.md",
                    article_name="domain",
                    snippet="Domain summary",
                    section="Directory Abstract",
                    level="L0",
                ),
                SourceSnippet(
                    article_path="/tmp/wiki/concept-a.md",
                    article_name="concept-a",
                    snippet="Concept details",
                    section="Compiled Truth",
                    level="L2",
                ),
            ],
        )
    )

    result = await query_tool.ainvoke({"question": "test"})
    sources = result["metadata"]["sources"]
    assert len(sources) == 2
    assert sources[0]["level"] == "L0"
    assert sources[0]["path"] == "domain/.abstract.md"
    assert sources[1]["level"] == "L2"
    assert sources[1]["path"] == "/tmp/wiki/concept-a.md"


@pytest.mark.asyncio
async def test_wiki_query_asset_only_returns_sources(direct_mock_tools: DirectMockTools) -> None:
    """Asset-only wiki hits must not early-exit when related_articles is empty."""
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

    tools, _, mock_qe = direct_mock_tools
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")

    mock_qe.query = AsyncMock(
        return_value=QueryResult(
            question="architecture diagram",
            answer="The diagram shows three tiers.",
            related_articles=[],
            confidence_score=0.5,
            source_snippets=[
                SourceSnippet(
                    article_path="wiki/assets/arch.png",
                    article_name="architecture",
                    snippet="Three-tier system diagram",
                    section="Image",
                    level="L2",
                    hit_kind="asset",
                    asset_filename="arch.png",
                )
            ],
        )
    )

    result = await query_tool.ainvoke({"question": "architecture diagram"})
    assert isinstance(result, dict)
    sources = result["metadata"]["sources"]
    assert len(sources) == 1
    assert sources[0]["hit_kind"] == "asset"
    assert "UNTRUSTED_DATA" in result["content"]


@pytest.mark.asyncio
async def test_wiki_query_injects_wiki_scope_id(wiki_structure: WikiStructure) -> None:
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

    mock_compiler = MagicMock(spec=WikiCompiler)
    mock_query_engine = MagicMock(spec=WikiQueryEngine)
    tools = create_wiki_tools(
        mock_compiler,
        mock_query_engine,
        wiki_structure,
        wiki_scope_id="agent-scope-42",
    )
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")
    mock_query_engine.query = AsyncMock(
        return_value=QueryResult(
            question="screenshot",
            answer="Image caption match",
            related_articles=["wiki/assets/sha_ui.png"],
            confidence_score=0.77,
            source_snippets=[
                SourceSnippet(
                    article_path="wiki/assets/sha_ui.png",
                    article_name="ui",
                    snippet="Login screen mockup",
                    section="Image",
                    level="L2",
                    hit_kind="asset",
                    asset_filename="sha_ui.png",
                )
            ],
        )
    )

    result = await query_tool.ainvoke({"question": "screenshot"})
    assert result["metadata"]["sources"][0]["agent_id"] == "agent-scope-42"


@pytest.mark.asyncio
async def test_wiki_query_emits_asset_source_metadata(direct_mock_tools: DirectMockTools) -> None:
    """wiki_query forwards asset hit metadata for chat thumbnails."""
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

    tools, _, mock_qe = direct_mock_tools
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")

    mock_qe.query = AsyncMock(
        return_value=QueryResult(
            question="screenshot",
            answer="Image caption match",
            related_articles=["wiki/assets/sha_ui.png"],
            confidence_score=0.77,
            source_snippets=[
                SourceSnippet(
                    article_path="wiki/assets/sha_ui.png",
                    article_name="ui",
                    snippet="Login screen mockup",
                    section="Image",
                    level="L2",
                    hit_kind="asset",
                    asset_filename="sha_ui.png",
                )
            ],
        )
    )

    result = await query_tool.ainvoke({"question": "screenshot"})
    sources = result["metadata"]["sources"]
    assert len(sources) == 1
    assert sources[0]["hit_kind"] == "asset"
    assert sources[0]["asset_filename"] == "sha_ui.png"


@pytest.mark.asyncio
async def test_wiki_query_emits_claim_snapshot_status(direct_mock_tools: DirectMockTools) -> None:
    """wiki_query should forward claim evidence snapshot_status to chat metadata sources."""
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

    tools, _, mock_qe = direct_mock_tools
    query_tool = next(t for t in tools if t.name == "wiki_query_tool")

    mock_qe.query = AsyncMock(
        return_value=QueryResult(
            question="Budget?",
            answer="Budget fact",
            related_articles=["/tmp/wiki/budget.md"],
            confidence_score=0.85,
            source_snippets=[
                SourceSnippet(
                    article_path="/tmp/wiki/budget.md",
                    article_name="budget",
                    snippet="Budget fact",
                    section="Claim",
                    level="L2",
                    claim_id="claim.budget",
                    claim_text="Budget fact",
                    evidence_path="raw/source.md",
                    line_range="1-3",
                    claim_status="supported",
                    evidence_content_sha256="abc123",
                    evidence_snapshot_status="stale",
                )
            ],
        )
    )

    result = await query_tool.ainvoke({"question": "Budget?"})
    sources = result["metadata"]["sources"]
    assert len(sources) == 1
    assert sources[0]["snapshot_status"] == "stale"
    assert sources[0]["claim_id"] == "claim.budget"
    assert sources[0]["claim_status"] == "supported"
    assert sources[0]["evidence_path"] == "raw/source.md"
    assert sources[0]["resource_uri"] == "raw/source.md@sha256:abc123"
    assert "claim.budget" in str(sources[0]["source_key"])
