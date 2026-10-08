"""Integration tests for Goal-Driven Quadruple Retrieval and Reasoner Suite API endpoints.

[POS]
Server-side integration test suite verifying goal deconstruction, item indexing,
4-channel parallel recall, reasoner reranking, and scoped filtering.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.quadruple_retrieval_router import (
    router as quadruple_retrieval_router,
)
from app.services.memory.quadruple_retrieval_service import (
    get_quadruple_retrieval_service,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting quadruple retrieval router."""
    api_app = FastAPI()
    api_app.include_router(quadruple_retrieval_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset quadruple retrieval service state before each test."""
    service = get_quadruple_retrieval_service()
    service.clear()


@pytest.mark.asyncio
async def test_parse_task_goal_api(test_app: FastAPI) -> None:
    """Verify pre-retrieval task goal decomposition endpoint."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        query = "如何配置 PostgreSQL 的 connection_pool 和 timeout 参数？"
        resp = await client.post(
            "/api/memory/retrieval/quadruple/parse-goal",
            params={"query": query},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["original_query"] == query
        assert data["explicit_intent"] == "procedural"
        assert len(data["target_entities"]) >= 1
        assert any("postgresql" in e.lower() for e in data["target_entities"])


@pytest.mark.asyncio
async def test_ingest_and_search_memories_api(test_app: FastAPI) -> None:
    """Verify memory item indexing and goal-driven quadruple search with reasoner reranking."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest items
        item_1 = {
            "memory_id": "mem_pg_active",
            "content": "PostgreSQL database connection timeout statement is configured to 30 seconds",
            "subject": "PostgreSQL",
            "predicate": "timeout",
            "object_value": "30s",
            "metadata": {"status": "active", "cube_id": "cube_infra"},
        }
        item_2 = {
            "memory_id": "mem_pg_deprecated",
            "content": "PostgreSQL connection timeout was 10s in legacy deprecated configuration",
            "subject": "PostgreSQL",
            "predicate": "timeout",
            "object_value": "10s",
            "metadata": {"status": "deprecated", "cube_id": "cube_infra"},
        }
        item_3 = {
            "memory_id": "mem_tailwind",
            "content": "Frontend component styling strictly mandates TailwindCSS utility classes",
            "subject": "Frontend",
            "predicate": "css_framework",
            "object_value": "TailwindCSS",
            "metadata": {"status": "active", "cube_id": "cube_web"},
        }

        r1 = await client.post("/api/memory/retrieval/quadruple/items", json=item_1)
        assert r1.status_code == 201
        r2 = await client.post("/api/memory/retrieval/quadruple/items", json=item_2)
        assert r2.status_code == 201
        r3 = await client.post("/api/memory/retrieval/quadruple/items", json=item_3)
        assert r3.status_code == 201

        # 2. Verify listing indexed items
        list_resp = await client.get("/api/memory/retrieval/quadruple/items")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 3

        # 3. Search query
        search_payload = {
            "query": "PostgreSQL connection timeout specifications",
            "top_k": 5,
        }
        search_resp = await client.post(
            "/api/memory/retrieval/quadruple/search",
            json=search_payload,
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()

        assert search_data["query"] == "PostgreSQL connection timeout specifications"
        assert search_data["fused_candidates_count"] >= 1
        assert len(search_data["final_hits"]) >= 1

        top_hit = search_data["final_hits"][0]
        assert top_hit["memory_id"] == "mem_pg_active"
        assert top_hit["final_rank"] == 1
        assert top_hit["reasoner_decision"] == "boost"
        assert "boosted" in top_hit["rationale"].lower()


@pytest.mark.asyncio
async def test_scoped_cube_filtering_api(test_app: FastAPI) -> None:
    """Verify scoped filtering isolates candidates to the designated memory cube."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest items in different cubes
        await client.post(
            "/api/memory/retrieval/quadruple/items",
            json={
                "memory_id": "mem_cube_a",
                "content": "Redis cache eviction policy is volatile-lru",
                "subject": "Redis",
                "predicate": "eviction",
                "object_value": "volatile-lru",
                "metadata": {"cube_id": "cube_alpha"},
            },
        )
        await client.post(
            "/api/memory/retrieval/quadruple/items",
            json={
                "memory_id": "mem_cube_b",
                "content": "Redis cache eviction policy is allkeys-lru",
                "subject": "Redis",
                "predicate": "eviction",
                "object_value": "allkeys-lru",
                "metadata": {"cube_id": "cube_beta"},
            },
        )

        # Search scoped only to cube_alpha
        resp = await client.post(
            "/api/memory/retrieval/quadruple/search",
            json={
                "query": "Redis cache eviction",
                "scoped_filters": {"cube_id": "cube_alpha"},
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        hits = resp.json()["final_hits"]
        assert len(hits) == 1
        assert hits[0]["memory_id"] == "mem_cube_a"


@pytest.mark.asyncio
async def test_empty_and_fallback_search_api(test_app: FastAPI) -> None:
    """Verify graceful handling when no memory matches or query is blank."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/retrieval/quadruple/search",
            json={"query": "nonexistent keywords entirely absent from store", "top_k": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fused_candidates_count"] == 0
        assert data["final_hits"] == []
