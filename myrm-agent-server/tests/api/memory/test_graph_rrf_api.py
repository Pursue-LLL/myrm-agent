"""
[POS] tests/api/memory/test_graph_rrf_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.graph_rrf_router
[OUTPUT] test_node_and_edge_crud, test_memory_association_and_traversal, test_dual_channel_search
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.graph_rrf_router import router as graph_rrf_router


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting graph_rrf router."""
    test_app = FastAPI()
    test_app.include_router(graph_rrf_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_node_and_edge_crud(client: TestClient) -> None:
    """Verify node and edge creation endpoints."""
    # 1. Create Node A
    resp_a = client.post(
        "/api/memory/graph-rrf/nodes",
        json={
            "id": "node-alpha",
            "name": "AlphaSystem",
            "entity_type": "service",
            "properties": {"tier": "critical"},
        },
    )
    assert resp_a.status_code == 201
    data_a = resp_a.json()
    assert data_a["id"] == "node-alpha"
    assert data_a["name"] == "AlphaSystem"

    # 2. Get Node A
    get_resp = client.get("/api/memory/graph-rrf/nodes/node-alpha")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "AlphaSystem"

    # 3. Create Node B
    resp_b = client.post(
        "/api/memory/graph-rrf/nodes",
        json={
            "id": "node-beta",
            "name": "BetaGateway",
            "entity_type": "proxy",
            "properties": {"zone": "us-east"},
        },
    )
    assert resp_b.status_code == 201

    # 4. Create Edge A -> B
    resp_edge = client.post(
        "/api/memory/graph-rrf/edges",
        json={
            "id": "edge-ab",
            "source_id": "node-alpha",
            "target_id": "node-beta",
            "relation_type": "routes_traffic_to",
            "weight": 1.5,
            "properties": {"protocol": "grpc"},
        },
    )
    assert resp_edge.status_code == 201
    data_edge = resp_edge.json()
    assert data_edge["relation_type"] == "routes_traffic_to"


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
    assoc_resp = client.post(
        "/api/memory/graph-rrf/associate",
        json={
            "memory_id": "mem-auth-01",
            "entity_id": "node-svc",
            "content": "AuthService enforces JWT verification with RSA256.",
        },
    )
    assert assoc_resp.status_code == 200
    assert assoc_resp.json()["status"] == "success"

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
    client.post(
        "/api/memory/graph-rrf/associate",
        json={
            "memory_id": "mem-core-fact",
            "entity_id": "node-core",
            "content": "CoreEngine handles distributed state coordination.",
        },
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
