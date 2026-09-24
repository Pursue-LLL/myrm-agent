"""Test GET /api/v1/wiki/concepts/{name}/links endpoint."""

from dataclasses import dataclass
from pathlib import Path
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


def test_heading_markdown_syntax_stripping_and_alias_caching(tmp_path: Path):
    """Verify that headings with rich markdown formatting are stripped cleanly and alias cache works."""
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.retrieval.graph_store import _clean_heading_text

    # 1. Test markdown syntax stripping
    raw_heading = "## 4.2 **核心网关** 下的 `TokenBucket` [自适应限流](https://example.com/ratelimit)"
    cleaned = _clean_heading_text(raw_heading)
    assert cleaned == "4.2 核心网关 下的 TokenBucket 自适应限流"

    raw_heading_2 = "### 架构演进 [[链路设计|全景图]] ~~废弃逻辑~~"
    cleaned_2 = _clean_heading_text(raw_heading_2)
    assert cleaned_2 == "架构演进 全景图 废弃逻辑"

    # 2. Test alias mtime shared cache
    wiki = WikiStructure(tmp_path)
    wiki.ensure_structure()
    concept_file = wiki.concepts_dir / "ratelimit.md"
    concept_file.write_text(
        "---\naliases:\n  - 限流算法\n  - TokenBucket\n---\n# RateLimit\nContent",
        encoding="utf-8",
    )

    # First resolve builds cache
    res1 = wiki.resolve_alias_file_path("限流算法")
    assert res1 is not None and res1.name == "ratelimit.md"

    # Create a fresh WikiStructure instance for the same directory: should hit class-level mtime cache
    wiki2 = WikiStructure(tmp_path)
    res2 = wiki2.resolve_alias_file_path("TokenBucket")
    assert res2 is not None and res2.name == "ratelimit.md"

    # Invalidate cache clears correctly
    wiki2.invalidate_alias_cache()
    assert wiki2._alias_to_path_cache is None

