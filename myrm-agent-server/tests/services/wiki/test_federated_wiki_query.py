"""Tests for Federated Wiki Query — multi-vault mounting, label resolution, and cache isolation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

from app.services.wiki.knowledge_query_service import execute_wiki_knowledge_query
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.vault import (
    get_wiki_archiver,
    reset_wiki_archiver_cache_for_tests,
    resolve_shared_wiki_vault_labels,
    resolve_shared_wiki_vault_paths,
)


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="[]"))
    return llm


def test_resolve_shared_wiki_vault_labels() -> None:
    """Verify friendly label mapping for shared vaults."""
    context_ids = ["kb-hr-policy", "kb-finance-2026"]
    name_map = {
        "kb-hr-policy": "Human Resources Policy 2026",
        "kb-finance-2026": "Finance & Reimbursement Standards",
    }
    labels = resolve_shared_wiki_vault_labels(context_ids, context_name_map=name_map)

    # Check key by safe_id / context_id
    assert labels.get("kb-hr-policy") == "Human Resources Policy 2026"
    assert labels.get("kb-finance-2026") == "Finance & Reimbursement Standards"

    # Check key by stringified path
    paths = resolve_shared_wiki_vault_paths(context_ids)
    assert len(paths) == 2
    assert labels.get(str(paths[0])) == "Human Resources Policy 2026"
    assert labels.get(str(paths[1])) == "Finance & Reimbursement Standards"


def test_resolve_shared_wiki_vault_paths_cap_limit() -> None:
    """Verify resolve_shared_wiki_vault_paths caps at MAX_SHARED_WIKI_VAULTS (6)."""
    cids = [f"kb-{i}" for i in range(10)]
    paths = resolve_shared_wiki_vault_paths(cids)
    assert len(paths) == 6


def test_get_wiki_archiver_cache_isolation_by_public_dirs(mock_llm: MagicMock, tmp_path: Path) -> None:
    """Verify archiver cache keys isolate instances by attached public_dirs."""
    reset_wiki_archiver_cache_for_tests()

    dir_a = tmp_path / "shared_a"
    dir_b = tmp_path / "shared_b"
    dir_a.mkdir(parents=True, exist_ok=True)
    dir_b.mkdir(parents=True, exist_ok=True)

    # Instance 1: default with no mounted shared vaults
    archiver_default = get_wiki_archiver(mock_llm, agent_id="agent-1")
    assert len(archiver_default._structure.public_dirs) == 0

    # Instance 2: with dir_a mounted
    archiver_a = get_wiki_archiver(mock_llm, agent_id="agent-1", public_dirs=[dir_a])
    assert len(archiver_a._structure.public_dirs) == 1
    assert archiver_a is not archiver_default

    # Instance 3: with dir_a and dir_b mounted
    archiver_ab = get_wiki_archiver(mock_llm, agent_id="agent-1", public_dirs=[dir_a, dir_b])
    assert len(archiver_ab._structure.public_dirs) == 2
    assert archiver_ab is not archiver_a

    # Instance 4: fetch with identical public_dirs and labels -> should hit cache
    archiver_ab_cached = get_wiki_archiver(mock_llm, agent_id="agent-1", public_dirs=[dir_b, dir_a])
    assert archiver_ab_cached is archiver_ab

    # Instance 5: fetch with different labels -> should isolate cache
    archiver_ab_diff_labels = get_wiki_archiver(
        mock_llm, agent_id="agent-1", public_dirs=[dir_a, dir_b], public_dir_labels={str(dir_a): "Vault A"}
    )
    assert archiver_ab_diff_labels is not archiver_ab

    reset_wiki_archiver_cache_for_tests()


@pytest.mark.asyncio
async def test_execute_wiki_knowledge_query_with_federated_vaults(
    tmp_path: Path, mock_llm: MagicMock
) -> None:
    """Verify execute_wiki_knowledge_query attaches shared_context_ids and labels."""
    reset_wiki_archiver_cache_for_tests()

    shared_dir = tmp_path / "shared_kb"
    shared_dir.mkdir(parents=True, exist_ok=True)
    (shared_dir / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    concept_file = shared_dir / "wiki" / "concepts" / "policy.md"
    concept_file.write_text("# Company Policy\nAll travel expenses must be pre-approved.", encoding="utf-8")

    # Create mock archiver with query_wiki returning snippets from shared vault
    archiver = MemoryToWikiArchiver(
        llm=mock_llm,
        wiki_dir=tmp_path / "primary_wiki",
        public_dirs=[shared_dir],
        public_dir_labels={str(shared_dir): "Corporate Policy Vault"},
    )

    mock_snippet = SourceSnippet(
        article_path="policy",
        article_name="policy.md",
        snippet="All travel expenses must be pre-approved.",
    )
    mock_result = QueryResult(
        question="What is the travel policy?",
        answer="Travel expenses must be pre-approved per policy.",
        confidence_score=0.95,
        source_snippets=[mock_snippet],
        related_articles=["policy"],
    )
    archiver.query_wiki = AsyncMock(return_value=mock_result)

    result = await execute_wiki_knowledge_query(
        agent_id="test-agent",
        question="What is the travel policy?",
        archiver=archiver,
    )

    assert result.confidence_score == 0.95
    assert len(result.sources) == 1
    assert result.sources[0]["kb_name"] == "Corporate Policy Vault"
    assert "pre-approved" in result.answer

    reset_wiki_archiver_cache_for_tests()


def test_general_agent_resolves_wiki_public_dir_labels_from_context_names() -> None:
    """Verify GeneralAgent uses memory_shared_context_names without DB lookups."""
    from app.ai_agents.general_agent import GeneralAgent

    agent = GeneralAgent.__new__(GeneralAgent)
    agent.memory_shared_context_ids = ["kb-policy", "kb-security"]
    agent.memory_shared_context_names = {
        "kb-policy": "Company Policy 2026",
        "kb-security": "Security Guidelines",
    }

    labels = agent._resolve_wiki_public_dir_labels()
    assert labels.get("kb-policy") == "Company Policy 2026"
    assert labels.get("kb-security") == "Security Guidelines"

