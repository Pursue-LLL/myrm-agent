"""[POS]: tests/api/memory/test_temporal_graph_api.py
[INPUT]: Isolated FastAPI test application, AsyncClient, and temporary SQLite storage.
[OUTPUT]: Integration tests verifying temporal knowledge graph entity nodes, fact conflict resolution, lineage, and decay scoring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.temporal_graph_router import (
    router as temporal_graph_router,
)
from app.services.memory.temporal_graph_service import (
    TemporalGraphService,
    get_temporal_graph_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> TemporalGraphService:
    """Provides an isolated TemporalGraphService backed by a temporary SQLite file."""
    db_file = tmp_path / "test_temporal_graph_api.db"
    return TemporalGraphService(db_path=db_file)


@pytest.fixture
def test_app(isolated_service: TemporalGraphService) -> FastAPI:
    """Creates a FastAPI test application with dependency overrides."""
    app = FastAPI()
    app.include_router(temporal_graph_router, prefix="/api/memory")
    app.dependency_overrides[get_temporal_graph_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_temporal_graph_entity_nodes_crud_api(test_app: FastAPI) -> None:
    """Verifies creating, retrieving, listing, and deleting entity nodes."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create two entity nodes
        res1 = await client.post(
            "/api/memory/temporal-graph/nodes",
            json={
                "name": "Alice Developer",
                "entity_type": "user",
                "attributes": {"role": "Senior Architect"},
            },
        )
        assert res1.status_code == 200, res1.text
        node1 = res1.json()
        assert node1["name"] == "Alice Developer"
        assert node1["attributes"]["role"] == "Senior Architect"

        res2 = await client.post(
            "/api/memory/temporal-graph/nodes",
            json={
                "name": "TechCorp",
                "entity_type": "organization",
                "attributes": {"domain": "Cloud AI"},
            },
        )
        assert res2.status_code == 200
        node2 = res2.json()

        # 2. Get by ID
        res_get = await client.get(f"/api/memory/temporal-graph/nodes/{node1['node_id']}")
        assert res_get.status_code == 200
        assert res_get.json()["name"] == "Alice Developer"

        # 3. 404 for unknown ID
        res_404 = await client.get("/api/memory/temporal-graph/nodes/unknown_node")
        assert res_404.status_code == 404

        # 4. List nodes
        res_list = await client.get("/api/memory/temporal-graph/nodes")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 2

        # 5. Delete node
        res_del = await client.delete(f"/api/memory/temporal-graph/nodes/{node2['node_id']}")
        assert res_del.status_code == 200
        assert res_del.json()["deleted"] is True


@pytest.mark.asyncio
async def test_temporal_graph_fact_conflict_resolution_and_lineage_api(test_app: FastAPI) -> None:
    """Verifies mutually exclusive facts automatically supersede previous active facts and track evolutionary lineage."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_id = "user_bob"
        comp_a = "comp_startup_a"
        comp_b = "comp_cloud_b"
        comp_c = "comp_studio_c"

        # 1. First fact: Bob works_at StartupA
        res1 = await client.post(
            "/api/memory/temporal-graph/edges",
            json={
                "source_id": user_id,
                "target_id": comp_a,
                "predicate": "works_at",
                "confidence_score": 0.95,
            },
        )
        assert res1.status_code == 200, res1.text
        data1 = res1.json()
        assert data1["is_conflict_detected"] is False
        assert len(data1["superseded_edges"]) == 0
        edge1_id = data1["new_edge"]["edge_id"]

        # 2. Second fact: Bob works_at CloudB (Mutually exclusive conflict)
        res2 = await client.post(
            "/api/memory/temporal-graph/edges",
            json={
                "source_id": user_id,
                "target_id": comp_b,
                "predicate": "works_at",
                "confidence_score": 0.98,
            },
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["is_conflict_detected"] is True
        assert len(data2["superseded_edges"]) == 1
        assert data2["superseded_edges"][0]["edge_id"] == edge1_id
        edge2_id = data2["new_edge"]["edge_id"]

        # 3. Third fact: Bob works_at StudioC
        res3 = await client.post(
            "/api/memory/temporal-graph/edges",
            json={
                "source_id": user_id,
                "target_id": comp_c,
                "predicate": "works_at",
                "confidence_score": 1.0,
            },
        )
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["is_conflict_detected"] is True
        edge3_id = data3["new_edge"]["edge_id"]

        # 4. Query backward lineage of edge3: edge3 -> edge2 -> edge1
        res_lineage = await client.get(f"/api/memory/temporal-graph/edges/{edge3_id}/lineage")
        assert res_lineage.status_code == 200
        lineage_edges = res_lineage.json()
        assert len(lineage_edges) == 3
        assert [e["edge_id"] for e in lineage_edges] == [edge3_id, edge2_id, edge1_id]


@pytest.mark.asyncio
async def test_temporal_graph_decay_query_and_stats_api(test_app: FastAPI) -> None:
    """Verifies querying fact edges with dynamic decay scores and fetching graph stats."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register nodes for name resolution
        await client.post(
            "/api/memory/temporal-graph/nodes",
            json={"node_id": "u_dev", "name": "Developer Dave", "entity_type": "user"},
        )
        await client.post(
            "/api/memory/temporal-graph/nodes",
            json={"node_id": "lang_rust", "name": "Rust Language", "entity_type": "technology"},
        )

        # Insert edge
        await client.post(
            "/api/memory/temporal-graph/edges",
            json={
                "source_id": "u_dev",
                "target_id": "lang_rust",
                "predicate": "main_programming_language",
                "confidence_score": 1.0,
            },
        )

        # Query temporal facts
        res_query = await client.get("/api/memory/temporal-graph/query?source_id=u_dev")
        assert res_query.status_code == 200
        hits = res_query.json()
        assert len(hits) == 1
        assert hits[0]["source_node"]["name"] == "Developer Dave"
        assert hits[0]["target_node"]["name"] == "Rust Language"
        assert hits[0]["effective_status"] == "active"
        assert hits[0]["decayed_score"] > 0.9

        # Graph summary statistics
        res_stats = await client.get("/api/memory/temporal-graph/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["total_nodes_count"] == 2
        assert stats["active_edges_count"] == 1
        assert stats["superseded_edges_count"] == 0
        assert stats["average_decayed_score"] > 0.9
