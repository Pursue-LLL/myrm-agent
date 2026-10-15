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
        "outlinks": [{"name": "outgoing-dep", "exists": True}],
        "backlinks": [
            {
                "name": "source-article",
                "exists": True,
                "context_snippet": "This article depends on [[target-concept]].",
                "heading": "Detailed Architecture",
            },
            {
                "name": "root-summary",
                "exists": False,
                "context_snippet": "Mentions [[target-concept]] in lead.",
                "heading": None,
            },
        ],
        "outlinks_has_more": False,
        "backlinks_has_more": False,
    }
    mock_archiver._query_engine._indexer = mock_indexer

    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        response = client.get("/api/v1/wiki/concepts/target-concept/links")
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)

    assert response.status_code == 200, response.text
    mock_indexer.get_concept_links.assert_called_once_with("target-concept")
    assert response.json() == {
        "concept_name": "target-concept",
        "outlinks": [{"name": "outgoing-dep", "exists": True}],
        "backlinks": [
            {
                "name": "source-article",
                "exists": True,
                "context_snippet": "This article depends on [[target-concept]].",
                "heading": "Detailed Architecture",
            },
            {
                "name": "root-summary",
                "exists": False,
                "context_snippet": "Mentions [[target-concept]] in lead.",
                "heading": None,
            },
        ],
        "outlinks_has_more": False,
        "backlinks_has_more": False,
    }


def test_get_concept_links_reports_which_direction_was_cut(client: TestClient):
    """A direction cut at the indexer's cap is flagged on its own, so the UI can show "100+" for that side only."""
    mock_archiver = MagicMock()
    mock_indexer = MagicMock()
    mock_indexer.get_concept_links.return_value = {
        "concept_name": "hub",
        "outlinks": [],
        "backlinks": [{"name": "a", "exists": True, "context_snippet": None, "heading": None}],
        "outlinks_has_more": False,
        "backlinks_has_more": True,
    }
    mock_archiver._query_engine._indexer = mock_indexer

    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        response = client.get("/api/v1/wiki/concepts/hub/links")
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)

    assert response.status_code == 200, response.text
    assert response.json()["outlinks_has_more"] is False
    assert response.json()["backlinks_has_more"] is True


def test_get_concept_links_empty_and_cjk(client: TestClient):
    """Test edge cases with CJK characters and completely isolated concepts."""
    mock_archiver = MagicMock()
    mock_indexer = MagicMock()
    cjk_name = "分布式存储系统"
    mock_indexer.get_concept_links.return_value = {
        "concept_name": cjk_name,
        "outlinks": [],
        "backlinks": [],
        "outlinks_has_more": False,
        "backlinks_has_more": False,
    }
    mock_archiver._query_engine._indexer = mock_indexer

    from app.api.wiki.router import _get_wiki_archiver

    client.app.dependency_overrides[_get_wiki_archiver] = lambda: mock_archiver
    try:
        response = client.get(f"/api/v1/wiki/concepts/{cjk_name}/links")
    finally:
        client.app.dependency_overrides.pop(_get_wiki_archiver, None)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "concept_name": cjk_name,
        "outlinks": [],
        "backlinks": [],
        "outlinks_has_more": False,
        "backlinks_has_more": False,
    }


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
