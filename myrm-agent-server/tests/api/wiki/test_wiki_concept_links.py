"""Test GET /api/v1/wiki/concepts/{name}/links endpoint."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

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
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client():
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    return TestClient(app)


def test_get_concept_links_endpoint(client: TestClient):
    mock_archiver = MagicMock()
    mock_indexer = MagicMock()
    mock_indexer.get_concept_links.return_value = {
        "concept_name": "target-concept",
        "outlinks": [
            {
                "name": "outgoing-dep",
                "weight": 3.0,
                "exists": True,
                "context_snippet": None,
            }
        ],
        "backlinks": [
            {
                "name": "source-article",
                "weight": 3.5,
                "exists": True,
                "context_snippet": "This article depends on [[target-concept]].",
                "line_number": 42,
                "heading": "Detailed Architecture",
            },
            {
                "name": "root-summary",
                "weight": 1.0,
                "exists": True,
                "context_snippet": "Mentions [[target-concept]] in lead.",
                "line_number": None,
                "heading": None,
            },
        ],
        "ego_graph": {
            "nodes": [
                {"id": "target-concept", "name": "target concept", "group": 1},
                {"id": "outgoing-dep", "name": "outgoing dep", "group": 1},
                {"id": "source-article", "name": "source article", "group": 1},
            ],
            "edges": [
                {"source": "target-concept", "target": "outgoing-dep", "weight": 3.0},
                {"source": "source-article", "target": "target-concept", "weight": 3.5},
            ],
        },
    }
    mock_archiver._query_engine._indexer = mock_indexer

    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        response = client.get("/api/v1/wiki/concepts/target-concept/links")
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["concept_name"] == "target-concept"
    assert len(data["outlinks"]) == 1
    assert data["outlinks"][0]["name"] == "outgoing-dep"
    assert data["outlinks"][0]["weight"] == 3.0
    assert len(data["backlinks"]) == 2
    assert data["backlinks"][0]["name"] == "source-article"
    assert data["backlinks"][0]["context_snippet"] == "This article depends on [[target-concept]]."
    assert data["backlinks"][0]["line_number"] == 42
    assert data["backlinks"][0]["heading"] == "Detailed Architecture"
    assert data["backlinks"][1]["name"] == "root-summary"
    assert data["backlinks"][1]["line_number"] is None
    assert data["backlinks"][1]["heading"] is None
    assert len(data["ego_graph"]["nodes"]) == 3
    assert len(data["ego_graph"]["edges"]) == 2


def test_get_concept_links_empty_and_cjk(client: TestClient):
    """Test edge cases with CJK characters and completely isolated concepts."""
    mock_archiver = MagicMock()
    mock_indexer = MagicMock()
    cjk_name = "分布式存储系统"
    mock_indexer.get_concept_links.return_value = {
        "concept_name": cjk_name,
        "outlinks": [],
        "backlinks": [],
        "ego_graph": {
            "nodes": [{"id": cjk_name, "name": cjk_name, "group": 1}],
            "edges": [],
        },
    }
    mock_archiver._query_engine._indexer = mock_indexer

    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        response = client.get(f"/api/v1/wiki/concepts/{cjk_name}/links?depth=2")
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["concept_name"] == cjk_name
    assert data["outlinks"] == []
    assert data["backlinks"] == []
    assert len(data["ego_graph"]["nodes"]) == 1
    assert len(data["ego_graph"]["edges"]) == 0


def test_get_concept_links_invalid_depth(client: TestClient):
    """Test FastAPI validation when depth is out of bounds (ge=1, le=2)."""
    mock_archiver = MagicMock()
    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        # depth=0 is invalid (< 1)
        res_zero = client.get("/api/v1/wiki/concepts/test/links?depth=0")
        assert res_zero.status_code == 422

        # depth=3 is invalid (> 2)
        res_three = client.get("/api/v1/wiki/concepts/test/links?depth=3")
        assert res_three.status_code == 422
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)


def test_get_concept_links_error_handling(client: TestClient):
    """Test graceful 500 error response when indexer query throws an unexpected error."""
    mock_archiver = MagicMock()
    mock_indexer = MagicMock()
    mock_indexer.get_concept_links.side_effect = RuntimeError("Database disk I/O error")
    mock_archiver._query_engine._indexer = mock_indexer

    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        response = client.get("/api/v1/wiki/concepts/test/links")
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to fetch concept links"

