"""
[POS] tests/api/memory/test_zero_llm_memory_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.zero_llm_memory_router, myrm_agent_harness.toolkits.memory.zero_llm
[OUTPUT] test_extract_facts_api, test_search_memory_api, test_get_stats_api
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.zero_llm import ZeroLlmConfig, ZeroLlmMemoryEngine
from starlette.testclient import TestClient

from app.api.memory.zero_llm_memory_router import (
    router as zero_llm_memory_router,
)
from app.services.memory.zero_llm_memory_service import (
    ZeroLlmMemoryService,
    get_zero_llm_memory_service,
)


def _init_test_db(db_path: Path) -> None:
    """Initialize a test SQLite database with FTS5 table."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wiki_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_slug TEXT UNIQUE NOT NULL,
                scope_level TEXT NOT NULL,
                agent_profile_id TEXT,
                title TEXT NOT NULL,
                content TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts USING fts5(
                page_slug,
                title,
                content,
                content='wiki_pages',
                content_rowid='id'
            );
            """
        )
        pages: list[tuple[str, str, str | None, str, str]] = [
            (
                "zero-cost-arch",
                "global",
                None,
                "Zero Cost Architecture",
                "Pure deterministic rules and SQLite FTS5. See [[TopologyGuide]].",
            ),
            (
                "topology-guide",
                "global",
                None,
                "TopologyGuide",
                "Graph neighbors traversal via 1-hop [[Wikilink]] expansion.",
            ),
        ]
        for p in pages:
            cur = conn.execute(
                "INSERT INTO wiki_pages (page_slug, scope_level, agent_profile_id, title, content) VALUES (?, ?, ?, ?, ?)",
                p,
            )
            row_id = cur.lastrowid
            conn.execute(
                "INSERT INTO wiki_pages_fts (rowid, page_slug, title, content) VALUES (?, ?, ?, ?)",
                (row_id, p[0], p[3], p[4]),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def zero_llm_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Provide isolated TestClient fixture mounting zero-llm memory router."""
    db_file = tmp_path / "test_zero_llm.db"
    _init_test_db(db_file)
    engine = ZeroLlmMemoryEngine(db_path=db_file, config=ZeroLlmConfig())
    service = ZeroLlmMemoryService(engine=engine)

    test_app = FastAPI()
    test_app.include_router(zero_llm_memory_router, prefix="/api/memory")
    test_app.dependency_overrides[get_zero_llm_memory_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_extract_facts_api(zero_llm_client: TestClient) -> None:
    """Verify POST /api/memory/zero-llm/extract returns deterministic facts with 0 token cost."""
    payload = {
        "text": (
            "Please never use sudo in docker scripts. "
            "export REDIS_PORT=6379\n"
            "command exited with code 0\n"
            "We decided to adopt FastAPI framework."
        ),
        "turn_index": 1,
        "source_file": "setup.sh",
    }

    resp = zero_llm_client.post("/api/memory/zero-llm/extract", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["zero_token_cost"] is True
    assert data["total_extracted"] >= 3
    categories = {f["category"] for f in data["facts"]}
    assert "preference" in categories
    assert "configuration" in categories
    assert "tool_outcome" in categories


def test_search_memory_api(zero_llm_client: TestClient) -> None:
    """Verify POST /api/memory/zero-llm/search executes FTS5 matching and graph neighbor expansion."""
    payload = {
        "query": "deterministic rules FTS5",
        "profile_id": None,
        "limit": 5,
        "graph_hop_decay": 0.5,
    }

    resp = zero_llm_client.post("/api/memory/zero-llm/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["zero_token_cost"] is True
    assert data["total_hits"] >= 2
    # Verify primary hit and 1-hop graph neighbor
    hops = {h["graph_hops"] for h in data["hits"]}
    assert 0 in hops
    assert 1 in hops


def test_get_stats_api(zero_llm_client: TestClient) -> None:
    """Verify GET /api/memory/zero-llm/stats returns operational cost verification telemetry."""
    # First trigger one extraction to update counters
    zero_llm_client.post(
        "/api/memory/zero-llm/extract",
        json={"text": "never delete production database", "turn_index": 0},
    )

    resp = zero_llm_client.get("/api/memory/zero-llm/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert data["zero_token_cost"] is True
    assert data["total_extractions"] >= 1
    assert "augmentation_mode" in data
    assert "min_confidence" in data
