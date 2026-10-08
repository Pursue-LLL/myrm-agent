"""Integration tests for dual-engine hybrid search and graceful fallback API.

[POS]
Integration test verifying concurrent FTS + vector orchestration, multi-factor re-ranking,
graceful fallback on provider outages/timeouts, and circuit breaker telemetry/reset endpoints.

[INPUT]
- asyncio, datetime, fastapi, httpx.AsyncClient, pytest
- myrm_agent_harness.toolkits.memory (HybridSearchHit)
- app.api.memory.hybrid_search (get_hybrid_search_service, router)
- app.services.memory.hybrid_search (DualEngineHybridSearchService)

[OUTPUT]
- Test functions covering hybrid search API endpoints.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import HybridSearchHit

from app.api.memory.hybrid_search import (
    get_hybrid_search_service,
)
from app.api.memory.hybrid_search import (
    router as hybrid_search_router,
)
from app.services.memory.hybrid_search.provider import (
    DualEngineHybridSearchService,
)


@pytest.fixture
def isolated_service() -> DualEngineHybridSearchService:
    """Create isolated hybrid search service with fast recovery breaker."""
    return DualEngineHybridSearchService(
        failure_threshold=2,
        recovery_timeout_seconds=0.1,
    )


@pytest.fixture
def test_app(isolated_service: DualEngineHybridSearchService) -> FastAPI:
    """Create FastAPI test application with injected isolated service."""
    api_app = FastAPI()
    api_app.include_router(hybrid_search_router, prefix="/api/memory")
    api_app.dependency_overrides[get_hybrid_search_service] = lambda: isolated_service
    return api_app


@pytest.mark.asyncio
async def test_full_hybrid_search_endpoint(test_app: FastAPI, isolated_service: DualEngineHybridSearchService) -> None:
    """Verify standard dual-engine hybrid search with fused re-ranking."""
    now_str = datetime.now(UTC).isoformat()

    async def mock_fts(query: str, limit: int) -> list[HybridSearchHit]:
        return [
            HybridSearchHit(
                item_id="doc_common",
                title="Common Knowledge",
                content="Architecture principles of memory systems",
                score=0.40,
                text_score=0.40,
                created_at=now_str,
                exact_match=True,
            )
        ]

    async def mock_vec(query: str, limit: int) -> list[HybridSearchHit]:
        return [
            HybridSearchHit(
                item_id="doc_common",
                title="Common Knowledge",
                content="Architecture principles of memory systems",
                score=0.90,
                vector_score=0.90,
                created_at=now_str,
            ),
            HybridSearchHit(
                item_id="doc_semantic_only",
                title="Semantic Latent",
                content="Vector embeddings and topological spaces",
                score=0.85,
                vector_score=0.85,
                created_at=now_str,
            ),
        ]

    isolated_service.set_providers(mock_fts, mock_vec)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        payload = {
            "query_text": "memory systems",
            "top_k": 5,
            "min_score": 0.20,
            "vector_weight": 0.65,
            "text_weight": 0.35,
        }
        resp = await client.post("/api/memory/hybrid-search/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert "hits" in data
        assert "report" in data
        assert data["report"]["mode"] == "hybrid"
        assert data["report"]["fallback_reason"] == "none"
        assert data["report"]["circuit_state"] == "closed"
        assert len(data["hits"]) >= 1

        top_hit = data["hits"][0]
        assert top_hit["item_id"] == "doc_common"
        assert top_hit["exact_match"] is True


@pytest.mark.asyncio
async def test_graceful_fallback_on_provider_timeout(
    test_app: FastAPI, isolated_service: DualEngineHybridSearchService
) -> None:
    """Verify graceful fallback to FTS when vector engine times out."""
    now_str = datetime.now(UTC).isoformat()

    async def mock_fts(query: str, limit: int) -> list[HybridSearchHit]:
        return [
            HybridSearchHit(
                item_id="doc_fts_fallback",
                title="FTS Local Note",
                content="Database locking and WAL recovery",
                score=0.30,
                text_score=0.30,
                created_at=now_str,
            )
        ]

    async def mock_vector_timeout(query: str, limit: int) -> list[HybridSearchHit]:
        await asyncio.sleep(0.5)
        return []

    isolated_service.set_providers(mock_fts, mock_vector_timeout)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        payload = {
            "query_text": "database locking",
            "top_k": 5,
            "min_score": 0.20,
            "timeout_seconds": 0.05,
        }
        resp = await client.post("/api/memory/hybrid-search/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["report"]["mode"] == "fallback_fts"
        assert data["report"]["fallback_reason"] == "provider_timeout"
        assert len(data["hits"]) == 1
        assert data["hits"][0]["item_id"] == "doc_fts_fallback"


@pytest.mark.asyncio
async def test_circuit_breaker_telemetry_and_reset(
    test_app: FastAPI, isolated_service: DualEngineHybridSearchService
) -> None:
    """Verify circuit breaker trips to OPEN on failures and can be manually reset."""
    async def mock_fts(query: str, limit: int) -> list[HybridSearchHit]:
        return []

    async def mock_vector_err(query: str, limit: int) -> list[HybridSearchHit]:
        raise RuntimeError("Remote vector provider connection refused")

    isolated_service.set_providers(mock_fts, mock_vector_err)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Check initial status
        status_resp = await client.get("/api/memory/hybrid-search/circuit-status")
        assert status_resp.status_code == 200
        assert status_resp.json()["state"] == "closed"

        # 2. Trigger failures to trip circuit
        for _ in range(2):
            await client.post(
                "/api/memory/hybrid-search/query",
                json={"query_text": "test trip", "timeout_seconds": 1.0},
            )

        # 3. Check status is now open
        status_resp2 = await client.get("/api/memory/hybrid-search/circuit-status")
        assert status_resp2.status_code == 200
        assert status_resp2.json()["state"] == "open"
        assert status_resp2.json()["failure_count"] >= 2

        # 4. Reset breaker
        reset_resp = await client.post("/api/memory/hybrid-search/circuit-reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["success"] is True
        assert reset_resp.json()["current_state"] == "closed"

        # 5. Check status is back to closed
        status_resp3 = await client.get("/api/memory/hybrid-search/circuit-status")
        assert status_resp3.json()["state"] == "closed"
