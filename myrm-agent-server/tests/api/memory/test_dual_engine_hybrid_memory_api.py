# [POS]: tests/api/memory/test_dual_engine_hybrid_memory_api.py
# [INPUT]: FastAPI test app, AsyncClient, isolated HybridMemoryService
# [OUTPUT]: Tests verifying Item 133 adaptive RRF, recency decay, importance weighting, and circuit breaker APIs

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    HybridSearchResult,
)

from app.api.memory.hybrid_memory_router import router as hybrid_memory_router
from app.services.memory.hybrid_memory_service import (
    HybridMemoryService,
    get_hybrid_memory_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> HybridMemoryService:
    """Provides an isolated HybridMemoryService with mock vector provider."""
    db_file = tmp_path / "test_dual_engine_api.db"
    service = HybridMemoryService(db_path=db_file)
    return service


@pytest.fixture
def test_app(isolated_service: HybridMemoryService) -> FastAPI:
    """Creates a FastAPI test application with isolated hybrid memory service."""
    app = FastAPI()
    app.include_router(hybrid_memory_router, prefix="/api/memory")
    app.dependency_overrides[get_hybrid_memory_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_insert_and_get_with_importance_and_timestamp(test_app: FastAPI) -> None:
    """Verifies that importance score and timestamp are persisted and returned."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        now_ts = time.time()
        res_insert = await client.post(
            "/api/memory/hybrid/items",
            json={
                "item": {
                    "item_id": "doc_perf_01",
                    "title": "Database Connection Pool Tuning",
                    "content": "Configure HikariCP maximumPoolSize and leakDetectionThreshold.",
                    "tags": ["database", "performance"],
                    "importance": 0.85,
                    "timestamp": now_ts,
                }
            },
        )
        assert res_insert.status_code == 200
        assert res_insert.json()["is_success"] is True

        res_get = await client.get("/api/memory/hybrid/items/doc_perf_01")
        assert res_get.status_code == 200
        data = res_get.json()
        assert data["item_id"] == "doc_perf_01"
        assert abs(data["importance"] - 0.85) < 0.001
        assert abs(data["timestamp"] - now_ts) < 0.001


@pytest.mark.asyncio
async def test_adaptive_rrf_search_parameters(test_app: FastAPI) -> None:
    """Verifies custom Adaptive RRF parameters and result annotations."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed test items
        now_ts = time.time()
        for idx in range(3):
            await client.post(
                "/api/memory/hybrid/items",
                json={
                    "item": {
                        "item_id": f"mem_item_{idx}",
                        "title": f"Memory Optimization {idx}",
                        "content": f"Memory cache strategy and sliding window chunking {idx}.",
                        "tags": ["memory"],
                        "importance": 0.5 + idx * 0.2,
                        "timestamp": now_ts - idx * 3600.0,
                    }
                },
            )

        # Search with customized adaptive RRF parameters
        res = await client.post(
            "/api/memory/hybrid/items/search",
            json={
                "query": "sliding window chunking",
                "limit": 5,
                "enable_vector": False,
                "adaptive_rrf": {
                    "rrf_k": 30,
                    "fts_weight": 1.5,
                    "vector_weight": 1.0,
                    "importance_weight": 0.6,
                    "half_life_seconds": 7200.0,
                    "apply_recency_decay": True,
                },
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_hits"] >= 1
        first_hit = data["results"][0]
        assert "importance" in first_hit
        assert "recency_factor" in first_hit
        assert "is_degraded" in first_hit
        assert first_hit["is_degraded"] is False


@pytest.mark.asyncio
async def test_circuit_breaker_trip_reset_and_stats_api(
    test_app: FastAPI,
    isolated_service: HybridMemoryService,
) -> None:
    """Verifies trip, reset, and telemetry reporting endpoints for the embedding circuit breaker."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initial stats should be closed
        res_stats = await client.get("/api/memory/hybrid/circuit-breaker/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["state"] == "closed"
        assert stats["tripped_count"] == 0

        # 2. Trip breaker
        res_trip = await client.post(
            "/api/memory/hybrid/circuit-breaker/trip",
            json={"reason": "Simulated vector provider latency spike"},
        )
        assert res_trip.status_code == 200
        trip_data = res_trip.json()
        assert trip_data["is_success"] is True
        assert trip_data["state"] == "open"
        assert trip_data["tripped_count"] == 1

        # 3. Check stats reflects open
        res_stats_after = await client.get("/api/memory/hybrid/circuit-breaker/stats")
        assert res_stats_after.json()["state"] == "open"

        # 4. Insert item and search while open -> should return degraded_fallback
        await client.post(
            "/api/memory/hybrid/items",
            json={
                "item": {
                    "item_id": "trip_test_01",
                    "title": "Fallback Verification",
                    "content": "Verify graceful fallback when breaker is tripped.",
                    "tags": ["resilience"],
                }
            },
        )
        # Mock vector provider that would normally work
        isolated_service.set_vector_provider(
            lambda q, lim: [
                HybridSearchResult(
                    item_id="trip_test_01",
                    title="Fallback Verification",
                    content="Vector hit",
                    score=0.9,
                    source_channel="vector",
                )
            ]
        )

        res_search_open = await client.post(
            "/api/memory/hybrid/items/search",
            json={"query": "Fallback Verification", "limit": 5, "enable_vector": True},
        )
        assert res_search_open.status_code == 200
        search_data = res_search_open.json()
        assert search_data["mode"] == "degraded_fallback"
        assert search_data["results"][0]["is_degraded"] is True
        assert search_data["results"][0]["source_channel"] == "fts_degraded"

        # 5. Reset breaker
        res_reset = await client.post("/api/memory/hybrid/circuit-breaker/reset")
        assert res_reset.status_code == 200
        assert res_reset.json()["state"] == "closed"

        # 6. Subsequent search with healthy vector provider runs HYBRID_RRF
        res_search_closed = await client.post(
            "/api/memory/hybrid/items/search",
            json={"query": "Fallback Verification", "limit": 5, "enable_vector": True},
        )
        assert res_search_closed.status_code == 200
        closed_data = res_search_closed.json()
        assert closed_data["mode"] == "hybrid_rrf"
        assert closed_data["results"][0]["is_degraded"] is False
