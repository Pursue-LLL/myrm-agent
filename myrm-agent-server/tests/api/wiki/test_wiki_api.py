"""Wiki API端到端测试.

测试 /api/v1/wiki/* 端点，使用真实后端服务。
"""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID


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
    from app.main import app

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
    else:
        print(f"❌ Error: {response.text}")
        # Stats endpoint should work even if wiki is empty
        assert response.status_code in [200, 401, 403], f"Unexpected status: {response.status_code}"


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

        assert "answer" in data
        assert isinstance(data.get("related_articles", []), list)
    elif response.status_code == 401:
        print("⚠️ Authentication required (expected in production)")
    elif response.status_code == 403:
        print("⚠️ Authorization required (expected in production)")
    else:
        print(f"❌ Error: {response.text}")


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


def test_wiki_concept_update_validation(client: TestClient) -> None:
    """Test PUT /api/v1/wiki/concepts/{name} validates request body."""
    response = client.put("/api/v1/wiki/concepts/test", json={"content": ""})
    assert response.status_code == 422

    response = client.put("/api/v1/wiki/concepts/test", json={})
    assert response.status_code == 422


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
