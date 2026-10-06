"""
[POS] tests/api/memory/test_wiki_memory_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.wiki_memory_router, myrm_agent_harness.toolkits.memory.wiki_memory
[OUTPUT] test_save_and_get_wiki_page_api, test_search_and_backlinks_api, test_rebuild_index_and_history_api
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.wiki_memory import WikiMemoryEngine
from starlette.testclient import TestClient

from app.api.memory.wiki_memory_router import (
    router as wiki_memory_router,
)
from app.services.memory.wiki_memory_service import (
    WikiMemoryService,
    get_wiki_memory_service,
)


@pytest.fixture
def wiki_client(tmp_path: Path) -> TestClient:
    """Provide isolated TestClient fixture mounting wiki memory router with temp engine."""
    engine = WikiMemoryEngine(base_dir=tmp_path)
    service = WikiMemoryService(engine=engine)

    test_app = FastAPI()
    test_app.include_router(wiki_memory_router, prefix="/api/memory")
    test_app.dependency_overrides[get_wiki_memory_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_save_and_get_wiki_page_api(wiki_client: TestClient) -> None:
    """Verify POST /api/memory/wiki/pages and GET /api/memory/wiki/pages/{page_id}."""
    create_payload = {
        "page_id": "postgres_best_practices",
        "title": "Postgres Best Practices",
        "content": "Use connection pooler like PgBouncer. See [[DatabaseSharding]] for scale.",
        "scope": "global",
        "tags": ["postgres", "database"],
        "frontmatter": {"priority": "high"},
        "commit_message": "feat(wiki): add postgres best practices",
    }

    resp = wiki_client.post("/api/memory/wiki/pages", json=create_payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["page_id"] == "postgres_best_practices"
    assert data["title"] == "Postgres Best Practices"
    assert data["scope"] == "global"
    assert "postgres" in data["tags"]

    # Read back page
    get_resp = wiki_client.get("/api/memory/wiki/pages/postgres_best_practices?scope=global")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["page_id"] == "postgres_best_practices"
    assert "PgBouncer" in get_data["content"]


def test_search_and_backlinks_api(wiki_client: TestClient) -> None:
    """Verify FTS5 full-text search and Obsidian backlink graph endpoints."""
    # Seed two related pages
    p1 = {
        "page_id": "redis_cache_pattern",
        "title": "Redis Cache Pattern",
        "content": "Implement cache-aside strategy with [[CacheEviction]].",
        "scope": "global",
        "tags": ["redis", "cache"],
    }
    p2 = {
        "page_id": "memory_leak_audit",
        "title": "Memory Leak Audit",
        "content": "Review buffer allocations and [[CacheEviction]].",
        "scope": "global",
        "tags": ["memory"],
    }
    wiki_client.post("/api/memory/wiki/pages", json=p1)
    wiki_client.post("/api/memory/wiki/pages", json=p2)

    # 1. Search for Redis
    search_resp = wiki_client.post(
        "/api/memory/wiki/search",
        json={"query": "Redis", "limit": 5},
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total_matched"] >= 1
    assert search_data["matches"][0]["page_id"] == "redis_cache_pattern"

    # 2. Query backlinks to CacheEviction
    bl_resp = wiki_client.get("/api/memory/wiki/backlinks/CacheEviction")
    assert bl_resp.status_code == 200
    bl_data = bl_resp.json()
    assert bl_data["total_incoming"] == 2
    sources = [b["source_page_id"] for b in bl_data["backlinks"]]
    assert "redis_cache_pattern" in sources
    assert "memory_leak_audit" in sources


def test_rebuild_index_and_history_api(wiki_client: TestClient) -> None:
    """Verify index rebuild and git history endpoints."""
    # Create page
    page_payload = {
        "page_id": "ci_pipeline_setup",
        "title": "CI Pipeline Setup",
        "content": "Configure GitHub Actions workflows.",
        "scope": "global",
        "commit_message": "chore(wiki): setup ci pipeline page",
    }
    wiki_client.post("/api/memory/wiki/pages", json=page_payload)

    # Rebuild derived index from Markdown
    rebuild_resp = wiki_client.post("/api/memory/wiki/rebuild-index")
    assert rebuild_resp.status_code == 200
    rebuild_data = rebuild_resp.json()
    assert rebuild_data["status"] == "success"
    assert rebuild_data["rebuilt_pages"] >= 1

    # Check Git audit history
    hist_resp = wiki_client.get("/api/memory/wiki/history?limit=5")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] >= 1
    messages = [c["message"] for c in hist_data["commits"]]
    assert any("setup ci pipeline" in m for m in messages)
