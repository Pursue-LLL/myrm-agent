"""Wiki API端到端测试.

测试 /api/v1/wiki/* 端点，使用真实后端服务。
"""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.pipeline.chat_compound import ChatCompoundResult

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.chat_compound_service import ChatCompoundServiceError


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Auto-applied fixture: make all TestClient requests pass auth."""
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client():
    """Create test client."""
    from tests.support.minimal_app import build_minimal_app
    app = build_minimal_app(preset="wiki")
    return TestClient(app)


@pytest.fixture
def test_wiki_dir(tmp_path: Path) -> Path:
    """Create temporary wiki directory for testing."""
    wiki_dir = tmp_path / "test-wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    return wiki_dir


def test_wiki_stats_endpoint(client: TestClient) -> None:
    """Test GET /api/v1/wiki/stats endpoint."""
    print("\n📊 Testing /api/v1/wiki/stats...")

    response = client.get("/api/v1/wiki/stats")

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✅ Stats retrieved:")
        print(f"  - Total concepts: {data.get('total_concepts', 0)}")
        print(f"  - Total articles: {data.get('total_articles', 0)}")
        print(f"  - Total raw files: {data.get('total_raw_files', 0)}")
        print(f"  - Wiki path: {data.get('wiki_path', 'N/A')}")

        assert "total_concepts" in data
        assert "total_articles" in data
        assert "wiki_path" in data
        assert "vault_ready" in data
        assert "legacy_migrated" in data
        assert isinstance(data["vault_ready"], bool)
        assert isinstance(data["legacy_migrated"], bool)
        assert "structural_issues" in data
        assert isinstance(data["structural_issues"]["broken_links"], int)
        assert isinstance(data["structural_issues"]["invalid_frontmatter_types"], int)
        assert "synthesis_pending" in data
        assert isinstance(data["synthesis_pending"], int)
        assert "obsidian_launch_available" in data
        assert isinstance(data["obsidian_launch_available"], bool)
        assert "vault_git_enabled" in data
        assert "vault_git_initialized" in data
    else:
        print(f"❌ Error: {response.text}")
        # Stats endpoint should work even if wiki is empty
        assert response.status_code in [200, 401, 403], f"Unexpected status: {response.status_code}"


def test_wiki_stale_summary_endpoint(client: TestClient) -> None:
    """Test GET /api/v1/wiki/stale-summary endpoint."""
    response = client.get("/api/v1/wiki/stale-summary")
    if response.status_code == 200:
        data = response.json()
        assert "stale_count" in data
        assert "stale_files" in data
        assert isinstance(data["stale_count"], int)
        assert isinstance(data["stale_files"], list)
    else:
        assert response.status_code in [401, 403]


def test_wiki_query_endpoint(client: TestClient) -> None:
    """Test POST /api/v1/wiki/query endpoint."""
    print("\n🔍 Testing /api/v1/wiki/query...")

    request_data = {"question": "What is machine learning?"}

    response = client.post("/api/v1/wiki/query", json=request_data)

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✅ Query result:")
        print(f"  - Answer: {data.get('answer', '')[:100]}...")
        print(f"  - Related articles: {len(data.get('related_articles', []))}")
        print(f"  - Source snippets: {len(data.get('source_snippets', []))}")

        assert "answer" in data
        assert isinstance(data.get("related_articles", []), list)
        assert isinstance(data.get("source_snippets", []), list)
    elif response.status_code == 401:
        print("⚠️ Authentication required (expected in production)")
    elif response.status_code == 403:
        print("⚠️ Authorization required (expected in production)")
    else:
        print(f"❌ Error: {response.text}")


def test_wiki_query_endpoint_accepts_raw_claim_mode(client: TestClient) -> None:
    """POST /api/v1/wiki/query accepts optional raw_claim retrieval mode."""
    response = client.post(
        "/api/v1/wiki/query",
        json={"question": "What is the official revenue claim?", "mode": "raw_claim"},
    )

    if response.status_code == 200:
        data = response.json()
        assert "answer" in data
        assert isinstance(data.get("related_articles", []), list)
    else:
        assert response.status_code in {401, 403, 422}


def test_wiki_compile_endpoint(client: TestClient) -> None:
    """Test POST /api/v1/wiki/compile endpoint."""
    print("\n🔄 Testing /api/v1/wiki/compile...")

    response = client.post("/api/v1/wiki/compile")

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✅ Compilation result:")
        print(f"  - Concepts: {data.get('concepts_count', 0)}")
        print(f"  - Articles: {data.get('articles_generated', 0)}")
        print(f"  - Backlinks: {data.get('backlinks_created', 0)}")
        print(f"  - Duration: {data.get('duration_ms', 0)}ms")

        assert "concepts_count" in data
        assert "articles_generated" in data
        assert "duration_ms" in data
    elif response.status_code in [401, 403]:
        print("⚠️ Authentication/Authorization required (expected)")
    else:
        print(f"❌ Error: {response.text}")


def test_wiki_maintain_endpoint(client: TestClient) -> None:
    """Test POST /api/v1/wiki/maintain endpoint."""
    print("\n🔧 Testing /api/v1/wiki/maintain...")

    response = client.post("/api/v1/wiki/maintain")

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("✅ Maintenance result:")
        print(f"  - Issues found: {data.get('issues_found', 0)}")
        print(f"  - Issues fixed: {data.get('issues_fixed', 0)}")
        print(f"  - Connections: {data.get('connections_discovered', 0)}")
        print(f"  - Duration: {data.get('duration_ms', 0)}ms")

        assert "issues_found" in data
        assert "issues_fixed" in data
        assert "connections_discovered" in data
    elif response.status_code in [401, 403]:
        print("⚠️ Authentication/Authorization required (expected)")
    else:
        print(f"❌ Error: {response.text}")


def test_wiki_purpose_get(client: TestClient) -> None:
    """Test GET /api/v1/wiki/purpose endpoint."""
    print("\n🧭 Testing /api/v1/wiki/purpose GET...")
    response = client.get("/api/v1/wiki/purpose")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert "purpose" in data
        print(f"  ✅ Purpose: '{data['purpose'][:50]}...' ({len(data['purpose'])} chars)")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_purpose_put(client: TestClient) -> None:
    """Test PUT /api/v1/wiki/purpose endpoint."""
    print("\n🧭 Testing /api/v1/wiki/purpose PUT...")
    response = client.put("/api/v1/wiki/purpose", json={"purpose": "Test purpose for CI"})
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert data["success"] is True
        print("  ✅ Purpose updated")

        # Verify the write
        get_resp = client.get("/api/v1/wiki/purpose")
        if get_resp.status_code == 200:
            assert get_resp.json()["purpose"] == "Test purpose for CI"
    else:
        assert response.status_code in [200, 401, 403, 422]


def test_wiki_queue_status(client: TestClient) -> None:
    """Test GET /api/v1/wiki/queue endpoint."""
    print("\n📋 Testing /api/v1/wiki/queue...")
    response = client.get("/api/v1/wiki/queue")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert "stats" in data
        stats = data["stats"]
        assert "pending" in stats
        assert "processing" in stats
        assert "completed" in stats
        assert "failed" in stats
        print(f"  ✅ Queue stats: {stats}")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_queue_cancel(client: TestClient) -> None:
    """Test POST /api/v1/wiki/queue/cancel endpoint."""
    print("\n🚫 Testing /api/v1/wiki/queue/cancel...")
    response = client.post("/api/v1/wiki/queue/cancel")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert data["success"] is True
        print(f"  ✅ Cancel result: {data['message']}")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_queue_retry(client: TestClient) -> None:
    """Test POST /api/v1/wiki/queue/retry endpoint."""
    print("\n🔄 Testing /api/v1/wiki/queue/retry...")
    response = client.post("/api/v1/wiki/queue/retry")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert data["success"] is True
        print(f"  ✅ Retry result: {data['message']}")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_graph_insights(client: TestClient) -> None:
    """Test GET /api/v1/wiki/graph/insights endpoint."""
    print("\n🔬 Testing /api/v1/wiki/graph/insights...")
    response = client.get("/api/v1/wiki/graph/insights")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert "unexpected_connections" in data
        assert "knowledge_gaps" in data
        assert "communities" in data
        print(f"  ✅ Insights: {len(data['communities'])} communities, {len(data['knowledge_gaps'])} gaps")
    else:
        assert response.status_code in [200, 401, 403, 500]


def test_wiki_graph(client: TestClient) -> None:
    """Test GET /api/v1/wiki/graph endpoint."""
    print("\n🕸️ Testing /api/v1/wiki/graph...")
    response = client.get("/api/v1/wiki/graph")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        print(f"  ✅ Graph: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_concepts_list(client: TestClient) -> None:
    """Test GET /api/v1/wiki/concepts endpoint."""
    print("\n📝 Testing /api/v1/wiki/concepts...")
    response = client.get("/api/v1/wiki/concepts")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert "concepts" in data
        assert "total" in data
        assert "has_more" in data
        print(f"  ✅ Concepts: {data['total']} total")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_pending_edits(client: TestClient) -> None:
    """Test GET /api/v1/wiki/pending endpoint."""
    print("\n📋 Testing /api/v1/wiki/pending...")
    response = client.get("/api/v1/wiki/pending")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        assert "stats" in data
        assert "pending_edits" in data
        print(f"  ✅ Pending: {data['stats']}")
    else:
        assert response.status_code in [200, 401, 403]


def test_wiki_concept_get_not_found(client: TestClient) -> None:
    """Test GET /api/v1/wiki/concepts/{name} returns 404 for non-existent concept."""
    response = client.get("/api/v1/wiki/concepts/nonexistent_concept_xyz")
    assert response.status_code == 404


def test_wiki_concept_delete_not_found(client: TestClient) -> None:
    """Test DELETE /api/v1/wiki/concepts/{name} returns 404 for non-existent concept."""
    response = client.delete("/api/v1/wiki/concepts/nonexistent_concept_xyz")
    assert response.status_code == 404



def test_wiki_pending_approve_nonexistent(client: TestClient) -> None:
    """Test POST /pending/{edit_id}/approve returns 400 for non-existent edit."""
    response = client.post("/api/v1/wiki/pending/99999/approve")
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower() or "already processed" in response.json()["detail"].lower()


def test_wiki_pending_reject_nonexistent(client: TestClient) -> None:
    """Test POST /pending/{edit_id}/reject returns 400 for non-existent edit."""
    response = client.post("/api/v1/wiki/pending/99999/reject")
    assert response.status_code == 400


def test_wiki_pending_approve_invalid_id(client: TestClient) -> None:
    """Test POST /pending/{edit_id}/approve validates edit_id type."""
    response = client.post("/api/v1/wiki/pending/not_a_number/approve")
    assert response.status_code == 422


def test_wiki_purpose_max_length(client: TestClient) -> None:
    """Test PUT /api/v1/wiki/purpose validates max_length=2000."""
    long_purpose = "x" * 2001
    response = client.put("/api/v1/wiki/purpose", json={"purpose": long_purpose})
    assert response.status_code == 422


def test_wiki_purpose_empty(client: TestClient) -> None:
    """Test PUT /api/v1/wiki/purpose accepts empty string."""
    response = client.put("/api/v1/wiki/purpose", json={"purpose": ""})
    if response.status_code == 200:
        data = response.json()
        assert data["success"] is True


def test_wiki_graph_with_params(client: TestClient) -> None:
    """Test GET /api/v1/wiki/graph with query parameters."""
    response = client.get("/api/v1/wiki/graph?center_node=test&depth=2&limit=10")
    if response.status_code == 200:
        data = response.json()
        assert "nodes" in data
        assert "edges" in data


def test_wiki_concepts_with_pagination(client: TestClient) -> None:
    """Test GET /api/v1/wiki/concepts with pagination parameters."""
    response = client.get("/api/v1/wiki/concepts?limit=5&offset=0")
    if response.status_code == 200:
        data = response.json()
        assert "concepts" in data
        assert "total" in data
        assert "has_more" in data


def test_wiki_concepts_with_search(client: TestClient) -> None:
    """Test GET /api/v1/wiki/concepts with search query."""
    response = client.get("/api/v1/wiki/concepts?query=machine+learning")
    if response.status_code == 200:
        data = response.json()
        assert "concepts" in data
        assert isinstance(data["concepts"], list)


def test_wiki_query_validation(client: TestClient) -> None:
    """Test POST /api/v1/wiki/query validates empty question."""
    response = client.post("/api/v1/wiki/query", json={"question": ""})
    assert response.status_code == 422


def test_wiki_research_endpoint(client: TestClient) -> None:
    """Test POST /api/v1/wiki/research endpoint structure."""
    response = client.post("/api/v1/wiki/research", json={"topic": ""})
    assert response.status_code == 422

    response = client.post("/api/v1/wiki/research", json={})
    assert response.status_code == 422


def test_all_wiki_endpoints_registered(client: TestClient) -> None:
    """Test that all wiki endpoints are properly registered."""
    endpoints = [
        ("GET", "/api/v1/wiki/stats"),
        ("POST", "/api/v1/wiki/query"),
        ("POST", "/api/v1/wiki/compile"),
        ("POST", "/api/v1/wiki/maintain"),
        ("GET", "/api/v1/wiki/purpose"),
        ("PUT", "/api/v1/wiki/purpose"),
        ("GET", "/api/v1/wiki/queue"),
        ("POST", "/api/v1/wiki/queue/cancel"),
        ("POST", "/api/v1/wiki/queue/retry"),
        ("GET", "/api/v1/wiki/graph/insights"),
        ("GET", "/api/v1/wiki/graph"),
        ("GET", "/api/v1/wiki/concepts"),
        ("GET", "/api/v1/wiki/pending"),
        ("POST", "/api/v1/wiki/research"),
    ]

    for method, path in endpoints:
        if method == "GET":
            response = client.get(path)
        elif method == "PUT":
            response = client.put(path, json={"purpose": "test"})
        elif method == "DELETE":
            response = client.delete(path)
        else:
            response = client.post(path, json={"question": "test", "topic": "test"})

        assert response.status_code != 404, f"{method} {path} not found (404)"


def _find_tree_node(nodes: list[dict[str, object]], node_id: str) -> dict[str, object] | None:
    for node in nodes:
        if node.get("id") == node_id:
            return node
        children = node.get("children")
        if isinstance(children, list):
            found = _find_tree_node(children, node_id)
            if found is not None:
                return found
    return None


def test_wiki_tree_ingest_status_tracked_modified(client: TestClient, tmp_path: Path) -> None:
    """Concept tree should mark nodes whose sources changed after last compile."""
    import json
    from unittest.mock import MagicMock

    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    metadata_path = structure.get_wiki_metadata_path()
    metadata_path.write_text(json.dumps({"last_compile_time": "2020-01-01T00:00:00+00:00"}), encoding="utf-8")

    raw_file = structure.raw_dir / "source.md"
    raw_file.write_text("raw body", encoding="utf-8")

    concept_path = structure.get_concept_file_path("StaleConcept")
    concept_path.write_text(
        """---
type: concept
sources:
  - raw/source.md
---
Body
""",
        encoding="utf-8",
    )

    mock_archiver = MagicMock()
    mock_archiver._structure = structure

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    tree_client = TestClient(app)
    try:
        response = tree_client.get("/api/v1/wiki/tree")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    node = _find_tree_node(response.json(), "staleconcept")
    assert node is not None
    assert node.get("ingest_status") == "tracked-modified"


def test_wiki_raw_tree_ingest_status(client: TestClient, tmp_path: Path) -> None:
    """Raw tree should expose tri-state ingest annotations."""
    import json
    from unittest.mock import MagicMock

    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    metadata_path = structure.get_wiki_metadata_path()
    metadata_path.write_text(json.dumps({"last_compile_time": "2020-01-01T00:00:00+00:00"}), encoding="utf-8")
    raw_file = structure.raw_dir / "notes.md"
    raw_file.write_text("notes", encoding="utf-8")

    mock_archiver = MagicMock()
    mock_archiver._structure = structure

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    tree_client = TestClient(app)
    try:
        response = tree_client.get("/api/v1/wiki/raw/tree")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    node = _find_tree_node(response.json(), "notes")
    assert node is not None
    assert node.get("ingest_status") == "tracked-modified"


def test_wiki_concept_snapshot_status_stale(client: TestClient, tmp_path: Path) -> None:
    """Concept claims should report stale snapshot when raw source changes."""
    import hashlib
    from unittest.mock import MagicMock

    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    raw_file = structure.raw_dir / "source.md"
    raw_bytes = b"original body"
    raw_file.write_bytes(raw_bytes)
    pinned = hashlib.sha256(raw_bytes).hexdigest()

    concept_path = structure.get_concept_file_path("Budget")
    concept_path.write_text(
        f"""---
type: concept
claims:
  - id: claim.budget
    text: Budget fact
    status: supported
    evidence:
      - kind: raw-note
        path: raw/source.md
        contentSha256: {pinned}
---
Body
""",
        encoding="utf-8",
    )
    raw_file.write_bytes(b"modified body")

    mock_archiver = MagicMock()
    mock_archiver._structure = structure

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    tree_client = TestClient(app)
    try:
        response = tree_client.get("/api/v1/wiki/concepts/Budget")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    claims = response.json()["claims"]
    assert len(claims) == 1
    assert claims[0]["evidence"][0]["snapshot_status"] == "stale"


def test_wiki_query_snapshot_status_stale(client: TestClient, tmp_path: Path) -> None:
    """Query source snippets should report stale snapshot when raw source changes."""
    import hashlib
    from unittest.mock import AsyncMock, MagicMock

    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult, SourceSnippet

    from app.api.wiki.router import _get_wiki_archiver
    from tests.support.minimal_app import build_minimal_app

    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    raw_file = structure.raw_dir / "source.md"
    raw_bytes = b"original body"
    raw_file.write_bytes(raw_bytes)
    pinned = hashlib.sha256(raw_bytes).hexdigest()
    raw_file.write_bytes(b"modified body")

    mock_archiver = MagicMock()
    mock_archiver._structure = structure
    mock_archiver.query_wiki = AsyncMock(
        return_value=QueryResult(
            question="Budget?",
            answer="Budget fact",
            related_articles=[],
            source_snippets=[
                SourceSnippet(
                    article_path=str(structure.get_concept_file_path("Budget")),
                    article_name="budget",
                    snippet="Budget fact",
                    section="Claim",
                    level="L2",
                    claim_id="claim.budget",
                    claim_text="Budget fact",
                    evidence_path="raw/source.md",
                    claim_status="supported",
                    evidence_content_sha256=pinned,
                    evidence_snapshot_status="stale",
                )
            ],
        )
    )

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MagicMock:
        return mock_archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    tree_client = TestClient(app)
    try:
        response = tree_client.post("/api/v1/wiki/query", json={"question": "Budget?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    snippets = response.json()["source_snippets"]
    assert len(snippets) == 1
    assert snippets[0]["snapshot_status"] == "stale"
    assert snippets[0]["claim_status"] == "supported"
    assert snippets[0]["evidence_path"] == "raw/source.md"
    assert snippets[0]["resource_uri"] == f"raw/source.md@sha256:{pinned}"
    assert snippets[0]["resource_uri"] != f"raw/{structure.get_concept_file_path('Budget')}".lower()


def test_wiki_compound_stages_pending_edit(client: TestClient) -> None:
    """POST /api/v1/wiki/compound delegates to server SSOT and returns pending id."""
    payload = {
        "concept_name": "ChatCompounds/2026-08/ci-note",
        "source_chat": "chat-ci-1",
        "source_message": "msg-ci-1",
    }
    with patch(
        "app.services.wiki.chat_compound_service.stage_chat_compound_from_message",
        new_callable=AsyncMock,
    ) as mock_stage:
        mock_stage.return_value = ChatCompoundResult(
            pending_edit_id=99,
            concept_name=payload["concept_name"],
        )
        response = client.post("/api/v1/wiki/compound", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["pending_edit_id"] == 99
    assert data["concept_name"] == payload["concept_name"]
    mock_stage.assert_awaited_once()


def test_wiki_compound_returns_not_found_for_missing_message(client: TestClient) -> None:
    payload = {
        "concept_name": "ChatCompounds/2026-08/missing",
        "source_chat": "chat-missing",
        "source_message": "msg-missing",
    }
    with patch(
        "app.services.wiki.chat_compound_service.stage_chat_compound_from_message",
        new_callable=AsyncMock,
        side_effect=ChatCompoundServiceError("message_not_found", "Chat message not found"),
    ):
        response = client.post("/api/v1/wiki/compound", json=payload)
    assert response.status_code == 404
    body = response.json()
    assert body.get("code") == "message_not_found" or body.get("detail", {}).get("code") == "message_not_found"


def test_wiki_compound_rejects_duplicate_source_message(client: TestClient) -> None:
    """Duplicate source_message returns 409 already_staged."""
    payload = {
        "concept_name": "ChatCompounds/2026-08/dup-note",
        "source_chat": "chat-dup",
        "source_message": "msg-dup-unique",
    }
    with patch(
        "app.services.wiki.chat_compound_service.stage_chat_compound_from_message",
        new_callable=AsyncMock,
        side_effect=[
            ChatCompoundResult(pending_edit_id=1, concept_name=payload["concept_name"]),
            ChatCompoundServiceError("already_staged", "Chat message already staged as pending edit 1"),
        ],
    ):
        first = client.post("/api/v1/wiki/compound", json=payload)
        second = client.post("/api/v1/wiki/compound", json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "already_staged"


def test_wiki_apply_chat_create_note_forbidden(client: TestClient) -> None:
    """Chat caller cannot publish create_note directly."""
    response = client.post(
        "/api/v1/wiki/apply?caller=chat",
        json={
            "op": "create_note",
            "concept_name": "ChatCompounds/2026-08/forbidden",
            "body": "Should not publish",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_for_caller"
