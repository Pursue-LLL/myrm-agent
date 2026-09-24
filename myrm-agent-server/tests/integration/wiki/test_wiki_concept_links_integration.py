"""Integration tests for Wiki Concept Links full-lifecycle flow.

Verifies the end-to-end integration between WikiStructure, GraphStore,
Indexer, and the FastAPI concept-links endpoint without mocks on the critical path.
"""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig

from app.api.wiki.router import _get_wiki_archiver
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def wiki_vault(tmp_path: Path) -> Path:
    """Create a temporary wiki vault directory hierarchy."""
    vault = tmp_path / "wiki-vault"
    for subdir in ("concepts", "deliverables", "methods", "claims"):
        (vault / subdir).mkdir(parents=True, exist_ok=True)
    return vault


@pytest.fixture
def wiki_archiver(wiki_vault: Path) -> MemoryToWikiArchiver:
    """Initialize real MemoryToWikiArchiver with disk-backed SQLite indexer."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
    config = WikiConfig(
        enable_hybrid_search=False,
        enable_directory_sidecars=False,
        enable_asset_index=False,
    )
    return MemoryToWikiArchiver(
        mock_llm,
        wiki_dir=wiki_vault,
        config=config,
    )


@pytest.fixture
def wiki_client(wiki_archiver: MemoryToWikiArchiver) -> Iterator[TestClient]:
    """Provide TestClient with real wiki archiver dependency injection."""
    app = build_minimal_app(preset="wiki")
    app.dependency_overrides[_get_wiki_archiver] = lambda: wiki_archiver
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(_get_wiki_archiver, None)


@pytest.mark.integration
def test_concept_links_full_task_flow_e2e(
    wiki_vault: Path,
    wiki_archiver: MemoryToWikiArchiver,
    wiki_client: TestClient,
) -> None:
    struct = wiki_archiver._structure
    struct.ensure_structure()

    # 1. Populate real concept note with frontmatter aliases
    concept_file = struct.concepts_dir / "distributed_systems.md"
    concept_file.write_text(
        "---\n"
        "title: Distributed Systems\n"
        "aliases:\n"
        "  - 分布式系统\n"
        "  - Distributed Computing\n"
        "---\n\n"
        "# Distributed Systems Overview\n\n"
        "Core foundational architecture for modern cloud infrastructure.\n",
        encoding="utf-8",
    )

    # Existing outlink target
    outlink_existing = struct.concepts_dir / "networking_protocols.md"
    outlink_existing.write_text(
        "# Networking Protocols\n\nLow level transport layers.\n",
        encoding="utf-8",
    )

    # 2. Populate referencing assets across various types and heading structures
    # Deliverable with H2 heading and direct concept link
    deliverable_file = struct.get_deliverable_file_path("consensus_raft.md")
    deliverable_file.write_text(
        "# Raft Implementation\n\n"
        "Introduction to consensus.\n\n"
        "## 核心算法选型\n\n"
        "This section evaluates high availability within [[distributed_systems]] clusters.\n",
        encoding="utf-8",
    )

    # Method referencing alias under H3 heading
    method_file = struct.get_method_file_path("paxos_protocol")
    method_file.write_text(
        "# Paxos Protocol\n\n"
        "Historical background.\n\n"
        "### 一致性保障\n\n"
        "Formal mathematical proofs demonstrate safety in modern [[distributed_systems]] (分布式系统) setups.\n",
        encoding="utf-8",
    )

    # Claim referencing concept under H1 heading
    claim_file = struct.get_claim_file_path("scalability_claim")
    claim_file.write_text(
        "# 扩展性声明\n\n"
        "Empirical benchmarks assert linear scale in [[distributed_systems]].\n",
        encoding="utf-8",
    )

    indexer = wiki_archiver._query_engine._indexer
    indexer.upsert("distributed_systems", concept_file.read_text(encoding="utf-8"))
    indexer.upsert("networking_protocols", outlink_existing.read_text(encoding="utf-8"))

    # 3. Upsert directional edges in SQLite database
    # Ingoing edges to distributed_systems
    indexer.upsert_edges("consensus_raft", ["distributed_systems"])
    indexer.upsert_edges("paxos_protocol", ["distributed_systems"])
    indexer.upsert_edges("scalability_claim", ["distributed_systems"])
    # Outgoing edges from distributed_systems (one existing, one missing)
    indexer.upsert_edges(
        "distributed_systems",
        ["networking_protocols", "byzantine_fault_tolerance"],
    )

    # 4. Invoke API endpoint through HTTP TestClient
    response = wiki_client.get("/api/v1/wiki/concepts/distributed_systems/links?depth=1")
    assert response.status_code == 200, f"Expected 200, got: {response.text}"

    data = response.json()
    assert data["concept_name"] == "distributed_systems"

    # 5. Assert outlinks validation
    outlinks = {item["name"]: item for item in data["outlinks"]}
    assert len(outlinks) == 2
    assert "networking_protocols" in outlinks
    assert outlinks["networking_protocols"]["exists"] is True
    assert "byzantine_fault_tolerance" in outlinks
    assert outlinks["byzantine_fault_tolerance"]["exists"] is False

    # 6. Assert backlinks validation with extracted line numbers, headings, and snippets
    backlinks = {item["name"]: item for item in data["backlinks"]}
    assert len(backlinks) == 3

    # consensus_raft verification
    raft_link = backlinks["consensus_raft"]
    assert raft_link["exists"] is True
    assert raft_link["heading"] == "核心算法选型"
    assert raft_link["line_number"] == 7
    assert raft_link["context_snippet"] is not None
    assert "[[distributed_systems]]" in raft_link["context_snippet"]

    # paxos_protocol verification
    paxos_link = backlinks["paxos_protocol"]
    assert paxos_link["exists"] is True
    assert paxos_link["heading"] == "一致性保障"
    assert paxos_link["line_number"] == 7
    assert paxos_link["context_snippet"] is not None
    assert "[[distributed_systems]]" in paxos_link["context_snippet"]

    # scalability_claim verification
    claim_link = backlinks["scalability_claim"]
    assert claim_link["exists"] is True
    assert claim_link["heading"] == "扩展性声明"
    assert claim_link["line_number"] == 3
    assert claim_link["context_snippet"] is not None
    assert "[[distributed_systems]]" in claim_link["context_snippet"]

    # 7. Assert ego graph topology structure
    ego_graph = data["ego_graph"]
    assert isinstance(ego_graph["nodes"], list)
    assert isinstance(ego_graph["edges"], list)

    # 8. Assert isolated/nonexistent concept returns safe default structure
    empty_res = wiki_client.get("/api/v1/wiki/concepts/unlinked_concept/links")
    assert empty_res.status_code == 200
    empty_data = empty_res.json()
    assert empty_data["concept_name"] == "unlinked_concept"
    assert empty_data["outlinks"] == []
    assert empty_data["backlinks"] == []
    assert empty_data["ego_graph"]["nodes"] == []
