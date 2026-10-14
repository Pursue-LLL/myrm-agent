"""
[POS] tests/api/memory/test_graph_rrf_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.graph_rrf_router, app.services.memory.graph_rrf_service (seeds memory associations)
[OUTPUT] test_node_creation, test_memory_association_and_traversal, test_dual_channel_search
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.graph_rrf_router import router as graph_rrf_router
from app.services.memory.graph_rrf_service import get_graph_rrf_service


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting graph_rrf router."""
    test_app = FastAPI()
    test_app.include_router(graph_rrf_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_node_creation(client: TestClient) -> None:
    """Verify entity node creation endpoint."""
    resp = client.post(
        "/api/memory/graph-rrf/nodes",
        json={
            "id": "node-alpha",
            "name": "AlphaSystem",
            "entity_type": "service",
            "properties": {"tier": "critical"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "node-alpha"
    assert data["name"] == "AlphaSystem"
    assert data["entity_type"] == "service"
    assert data["properties"] == {"tier": "critical"}


def test_memory_association_and_traversal(client: TestClient) -> None:
    """Verify linking memory with node and traversing the graph."""
    # Register Node
    client.post(
        "/api/memory/graph-rrf/nodes",
        json={
            "id": "node-svc",
            "name": "AuthService",
            "entity_type": "microservice",
            "properties": {},
        },
    )

    # Link memory
    get_graph_rrf_service().store.associate_memory(
        memory_id="mem-auth-01",
        entity_id="node-svc",
        content="AuthService enforces JWT verification with RSA256.",
    )

    # Traverse from seed
    traverse_resp = client.post(
        "/api/memory/graph-rrf/traverse",
        json={
            "seed_entity_ids": ["node-svc"],
            "max_hops": 2,
        },
    )
    assert traverse_resp.status_code == 200
    t_data = traverse_resp.json()
    assert "mem-auth-01" in t_data["associated_memory_ids"]
    assert any(n["id"] == "node-svc" for n in t_data["nodes"])


def test_dual_channel_search(client: TestClient) -> None:
    """Verify dual channel RRF hybrid search endpoint."""
    # Setup node and linked memory
    client.post(
        "/api/memory/graph-rrf/nodes",
        json={
            "id": "node-core",
            "name": "CoreEngine",
            "entity_type": "engine",
            "properties": {},
        },
    )
    get_graph_rrf_service().store.associate_memory(
        memory_id="mem-core-fact",
        entity_id="node-core",
        content="CoreEngine handles distributed state coordination.",
    )

    # Execute search with vector candidate + graph seed
    search_payload = {
        "query": "How is state coordinated in CoreEngine?",
        "seed_entity_names": ["CoreEngine"],
        "vector_candidates": [
            {
                "memory_id": "mem-core-fact",
                "content": "CoreEngine handles distributed state coordination.",
                "score": 0.88,
                "rank": 1,
            },
            {
                "memory_id": "mem-unrelated",
                "content": "Unrelated documentation snippet.",
                "score": 0.70,
                "rank": 2,
            },
        ],
        "top_k": 5,
        "k": 60,
        "vector_weight": 1.0,
        "graph_weight": 1.0,
    }
    resp = client.post("/api/memory/graph-rrf/search", json=search_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_hits"] >= 1
    top_hit = body["results"][0]
    assert top_hit["memory_id"] == "mem-core-fact"
    assert "vector" in top_hit["hit_sources"]
    assert "graph" in top_hit["hit_sources"]
    assert top_hit["vector_rank"] == 1
    assert top_hit["graph_rank"] is not None
