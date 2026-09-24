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
            }
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
    assert len(data["backlinks"]) == 1
    assert data["backlinks"][0]["name"] == "source-article"
    assert data["backlinks"][0]["context_snippet"] == "This article depends on [[target-concept]]."
    assert len(data["ego_graph"]["nodes"]) == 3
    assert len(data["ego_graph"]["edges"]) == 2
