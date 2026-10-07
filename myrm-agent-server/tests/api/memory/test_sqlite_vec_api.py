# [POS] tests/api/memory/test_sqlite_vec_api.py
# [INPUT] FastAPI, httpx.AsyncClient, tmp_path, app.api.memory.sqlite_vec
# [OUTPUT] TestSqliteVecAPISuite

"""Integration tests for embedded SQLite vector engine API and decay retrieval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.vector.base import VectorDocument

from app.api.memory.sqlite_vec import (
    get_sqlite_vec_provider,
)
from app.api.memory.sqlite_vec import (
    router as sqlite_vec_router,
)
from app.services.memory.sqlite_vec.provider import SqliteVecProvider


@pytest.fixture
def isolated_provider(tmp_path: Path) -> SqliteVecProvider:
    """Create isolated provider instance backed by temporary test database."""
    db_file = tmp_path / "test_api_vector.db"
    return SqliteVecProvider(db_path=str(db_file))


@pytest.fixture
def test_app(isolated_provider: SqliteVecProvider) -> FastAPI:
    """Create FastAPI test application with injected isolated provider."""
    api_app = FastAPI()
    api_app.include_router(sqlite_vec_router, prefix="/api/memory")
    api_app.dependency_overrides[get_sqlite_vec_provider] = lambda: isolated_provider
    return api_app


@pytest.mark.asyncio
async def test_sqlite_vec_stats_and_health(
    test_app: FastAPI, isolated_provider: SqliteVecProvider
) -> None:
    """Verify stats and health probe endpoints."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        health_resp = await client.get("/api/memory/sqlite-vec/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["healthy"] is True
        assert health_data["engine"] == "sqlite-vec"

        # 2. Stats
        stats_resp = await client.get("/api/memory/sqlite-vec/stats")
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["status"] == "healthy"
        assert stats_data["is_persistent"] is True
        assert stats_data["collection_count"] == 0
        assert stats_data["total_documents"] == 0
        assert stats_data["engine_mode"] in ("native_vec0", "process_blob")


@pytest.mark.asyncio
async def test_sqlite_vec_search_api_with_decay(
    test_app: FastAPI, isolated_provider: SqliteVecProvider
) -> None:
    """Verify vector search API with temporal decay attenuation."""
    coll = "api_test_memory"
    await isolated_provider.store.ensure_collection(coll, dimension=2)

    now = datetime.now(UTC)
    doc_fresh = VectorDocument(
        id="fresh_item",
        content="Latest architectural standard",
        vector=[1.0, 0.0],
        metadata={"category": "spec"},
        created_at=now,
    )
    doc_stale = VectorDocument(
        id="stale_item",
        content="Outdated obsolete draft",
        vector=[1.0, 0.0],  # Exactly identical cosine vector
        metadata={"category": "spec"},
        created_at=now - timedelta(days=14),
    )
    await isolated_provider.store.upsert(coll, [doc_fresh, doc_stale])

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Query with temporal decay applied
        resp = await client.post(
            "/api/memory/sqlite-vec/search",
            json={
                "collection": coll,
                "query_vector": [1.0, 0.0],
                "limit": 5,
                "apply_decay": True,
                "half_life_seconds": 86400.0 * 2,  # 2 days half life
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["collection"] == coll
        assert data["count"] == 2
        items = data["items"]
        assert items[0]["id"] == "fresh_item"
        assert items[1]["id"] == "stale_item"
        assert items[0]["score"] > items[1]["score"]
        assert items[0]["decay_factor"] is not None
        assert items[1]["decay_factor"] is not None
        assert items[0]["decay_factor"] > items[1]["decay_factor"]


@pytest.mark.asyncio
async def test_sqlite_vec_search_api_without_decay(
    test_app: FastAPI, isolated_provider: SqliteVecProvider
) -> None:
    """Verify vector search API returns unattenuated raw similarity when decay disabled."""
    coll = "raw_test_memory"
    await isolated_provider.store.ensure_collection(coll, dimension=2)

    now = datetime.now(UTC)
    doc1 = VectorDocument(
        id="item_a",
        content="Item A",
        vector=[1.0, 0.0],
        created_at=now,
    )
    doc2 = VectorDocument(
        id="item_b",
        content="Item B",
        vector=[1.0, 0.0],
        created_at=now - timedelta(days=30),
    )
    await isolated_provider.store.upsert(coll, [doc1, doc2])

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/sqlite-vec/search",
            json={
                "collection": coll,
                "query_vector": [1.0, 0.0],
                "limit": 5,
                "apply_decay": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        items = data["items"]
        # Raw scores must be identical
        assert pytest.approx(items[0]["score"], rel=1e-3) == items[1]["score"]
        assert items[0]["decay_factor"] == 1.0
        assert items[1]["decay_factor"] == 1.0
