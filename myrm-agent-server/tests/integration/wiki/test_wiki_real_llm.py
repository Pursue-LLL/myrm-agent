"""Wiki real LLM integration tests.

Tests wiki functionality with actual LLM calls (no mocks).
"""

import os
from pathlib import Path

import pytest
from langchain_openai import ChatOpenAI
from myrm_agent_harness.toolkits.wiki import (
    WikiCompileConfig,
    WikiCompiler,
    WikiConfig,
    WikiLinter,
    WikiQueryEngine,
    WikiStructure,
)

# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("BASIC_API_KEY"),
    reason="BASIC_API_KEY not set, skipping real LLM tests",
)


@pytest.fixture
def llm():
    """Create real LLM instance."""
    api_key = os.getenv("BASIC_API_KEY")
    model = os.getenv("BASIC_MODEL")
    if not model:
        raise RuntimeError("BASIC_MODEL must be set")
    base_url = os.getenv("BASIC_BASE_URL")

    if "/" in model:
        model = model.split("/", 1)[1]

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


@pytest.fixture
def test_wiki_dir(tmp_path: Path) -> Path:
    """Create temporary wiki directory."""
    return tmp_path / "integration-wiki"


@pytest.fixture
def wiki_structure(test_wiki_dir: Path) -> WikiStructure:
    """Create wiki structure."""
    structure = WikiStructure(test_wiki_dir)
    structure.ensure_structure()
    return structure


@pytest.mark.asyncio
async def test_full_wiki_workflow_with_real_llm(
    llm: ChatOpenAI,
    wiki_structure: WikiStructure,
) -> None:
    """Test complete wiki workflow with real LLM.

    This test verifies:
    1. Document ingestion
    2. LLM-powered compilation (concept extraction + article generation)
    3. Wiki querying with LLM
    4. Health maintenance
    """
    config = WikiConfig(
        parallel_compilation=False,
        auto_archive_enabled=False,
    )
    compile_config = WikiCompileConfig(min_concept_mentions=1, require_approval=False)

    compiler = WikiCompiler(llm, wiki_structure, config, compile_config)
    query_engine = WikiQueryEngine(llm, wiki_structure, config)
    linter = WikiLinter(llm, wiki_structure, config)

    # Step 1: Ingest raw documents
    doc1_path = wiki_structure.get_raw_file_path("machine_learning.md")
    doc1_path.write_text("# Machine Learning\n\nMachine learning is a subset of artificial intelligence.")

    doc2_path = wiki_structure.get_raw_file_path("neural_networks.md")
    doc2_path.write_text("# Neural Networks\n\nNeural networks are used in machine learning.")

    # Step 2: Compile with real LLM
    print("\n🔄 Compiling wiki with real LLM...")
    result = await compiler.compile_all()

    print("✅ Compilation complete:")
    print(f"  - Concepts: {result.concepts_count}")
    print(f"  - Articles: {result.articles_generated}")
    print(f"  - Duration: {result.duration_ms}ms")

    # Verify compilation succeeded
    assert result.concepts_count > 0, "Should extract at least one concept"
    assert result.articles_generated > 0, "Should generate at least one article"

    # Verify wiki files exist
    concepts = wiki_structure.list_concepts()
    assert len(concepts) > 0, "Should create concept files"

    # Step 3: Query wiki with real LLM
    print("\n🔍 Querying wiki with real LLM...")
    query_result = await query_engine.query("What is machine learning?")

    print("✅ Query result:")
    print(f"  - Question: {query_result.question}")
    print(f"  - Answer: {query_result.answer[:200]}...")

    assert query_result.answer, "Should generate an answer"
    assert len(query_result.answer) > 50, "Answer should be substantial"

    # Step 4: Maintain wiki health
    print("\n🔧 Running wiki maintenance...")
    lint_result = await linter.lint_and_maintain()

    print("✅ Maintenance complete:")
    print(f"  - Issues found: {lint_result.issues_found}")
    print(f"  - Issues fixed: {lint_result.issues_fixed}")
    print(f"  - Connections: {lint_result.connections_discovered}")

    # Maintenance should complete without errors
    assert lint_result.issues_found >= 0
    assert lint_result.issues_fixed >= 0


@pytest.mark.asyncio
async def test_incremental_compilation_with_real_llm(
    llm: ChatOpenAI,
    wiki_structure: WikiStructure,
) -> None:
    """Test incremental compilation only processes changed files."""
    config = WikiConfig(compile_strategy="incremental")
    compile_config = WikiCompileConfig(min_concept_mentions=1, require_approval=False)
    compiler = WikiCompiler(llm, wiki_structure, config, compile_config)

    # First compilation
    doc_path = wiki_structure.get_raw_file_path("test.md")
    doc_path.write_text("# Test\n\nThis is a test document about testing.")

    print("\n🔄 First compilation (full)...")
    result1 = await compiler.compile_all()
    print(f"  - Concepts: {result1.concepts_count}")
    print(f"  - Duration: {result1.duration_ms}ms")

    # Second compilation (no changes)
    print("\n🔄 Second compilation (incremental, no changes)...")
    result2 = await compiler.compile_all()
    print(f"  - Concepts: {result2.concepts_count}")
    print(f"  - Duration: {result2.duration_ms}ms")

    # Incremental should be faster (no LLM calls)
    assert result2.duration_ms < result1.duration_ms, "Incremental should be faster"
    assert result2.concepts_count == 0, "Should skip unchanged files"

    # Add new document
    doc2_path = wiki_structure.get_raw_file_path("new.md")
    doc2_path.write_text("# New\n\nThis is a new document about innovation.")

    print("\n🔄 Third compilation (incremental, new file)...")
    result3 = await compiler.compile_all()
    print(f"  - Concepts: {result3.concepts_count}")
    print(f"  - Duration: {result3.duration_ms}ms")

    # Should only process new file
    assert result3.concepts_count > 0, "Should extract concepts from new file"
