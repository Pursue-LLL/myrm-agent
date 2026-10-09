"""Integration tests for Graph Memory Reorganization and Lineage Traceability API endpoints.

[POS]
Server-side integration test suite for memory graph mutations, non-destructive evolution,
historical version reversion, lineage audit trails, and graph reorganization.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.graph_memory_router import router as graph_memory_router
from app.services.memory.graph_memory_service import get_graph_memory_service


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting graph memory router."""
    api_app = FastAPI()
    api_app.include_router(graph_memory_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset graph memory service state before each test."""
    service = get_graph_memory_service()
    service.clear()


@pytest.mark.asyncio
async def test_create_and_get_node_api(test_app: FastAPI) -> None:
    """Verify creating a graph node and retrieving it via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_payload = {
            "subject": "database",
            "predicate": "connection_timeout",
            "object_value": "30s",
            "content": "Database connection timeout is 30s",
            "confidence": 0.95,
            "source_session_id": "sess_infra_01",
            "evidence_quote": "Timeout set to 30s in config",
            "metadata": {"env": "prod"},
        }
        resp = await client.post("/api/memory/graph/nodes", json=create_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["subject"] == "database"
        assert data["predicate"] == "connection_timeout"
        assert data["object_value"] == "30s"
        assert data["version"] == 1
        assert data["status"] == "active"
        node_id = data["node_id"]

        # Fetch by ID
        get_resp = await client.get(f"/api/memory/graph/nodes/{node_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["node_id"] == node_id
        assert get_data["content"] == "Database connection timeout is 30s"

        # List with filter
        list_resp = await client.get(
            "/api/memory/graph/nodes",
            params={"subject": "database", "active_only": True},
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data) == 1
        assert list_data[0]["node_id"] == node_id


@pytest.mark.asyncio
async def test_evolve_and_lineage_traceability_api(test_app: FastAPI) -> None:
    """Verify non-destructive node evolution and full DAG lineage trace."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create root node
        resp = await client.post(
            "/api/memory/graph/nodes",
            json={
                "subject": "cache",
                "predicate": "ttl",
                "object_value": "300s",
            },
        )
        assert resp.status_code == 201
        v1_id = resp.json()["node_id"]

        # 2. Evolve node
        evolve_payload = {
            "object_value": "600s",
            "rationale": "Mitigate cache miss bursts during peak hours",
            "metadata": {"tuned_by": "perf_engineer"},
        }
        evolve_resp = await client.post(
            f"/api/memory/graph/nodes/{v1_id}/evolve", json=evolve_payload
        )
        assert evolve_resp.status_code == 200
        v2_data = evolve_resp.json()
        assert v2_data["version"] == 2
        assert v2_data["status"] == "active"
        assert v2_data["object_value"] == "600s"
        v2_id = v2_data["node_id"]

        # 3. Check v1 status is now superseded
        v1_resp = await client.get(f"/api/memory/graph/nodes/{v1_id}")
        assert v1_resp.status_code == 200
        assert v1_resp.json()["status"] == "superseded"

        # 4. Trace lineage
        lineage_resp = await client.get(f"/api/memory/graph/nodes/{v2_id}/lineage")
        assert lineage_resp.status_code == 200
        lineage_data = lineage_resp.json()
        assert lineage_data["target_node"]["node_id"] == v2_id
        assert lineage_data["is_latest"] is True
        assert len(lineage_data["ancestor_nodes"]) == 1
        assert lineage_data["ancestor_nodes"][0]["node_id"] == v1_id
        assert len(lineage_data["steps"]) >= 1


@pytest.mark.asyncio
async def test_non_destructive_revert_api(test_app: FastAPI) -> None:
    """Verify non-destructive version reversion creates a new revision and retains DAG."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create v1
        resp = await client.post(
            "/api/memory/graph/nodes",
            json={
                "subject": "feature_flag",
                "predicate": "state",
                "object_value": "disabled",
            },
        )
        v1_id = resp.json()["node_id"]

        # Evolve to v2
        evolve_resp = await client.post(
            f"/api/memory/graph/nodes/{v1_id}/evolve",
            json={
                "object_value": "enabled",
                "rationale": "Rollout to canary group",
            },
        )
        v2_id = evolve_resp.json()["node_id"]

        # Revert back to v1
        revert_resp = await client.post(
            f"/api/memory/graph/nodes/{v2_id}/revert",
            json={
                "historical_node_id": v1_id,
                "rationale": "Canary errors detected, rolling back to disabled",
            },
        )
        assert revert_resp.status_code == 200
        v3_data = revert_resp.json()
        assert v3_data["version"] == 3
        assert v3_data["status"] == "active"
        assert v3_data["object_value"] == "disabled"

        # Verify v2 is now reverted
        v2_resp = await client.get(f"/api/memory/graph/nodes/{v2_id}")
        assert v2_resp.status_code == 200
        assert v2_resp.json()["status"] == "reverted"

        # Verify lineage contains ancestors
        lineage_resp = await client.get(
            f"/api/memory/graph/nodes/{v3_data['node_id']}/lineage"
        )
        assert lineage_resp.status_code == 200
        trail = lineage_resp.json()
        assert trail["is_latest"] is True
        assert len(trail["ancestor_nodes"]) >= 1


@pytest.mark.asyncio
async def test_edge_creation_and_graph_reorganization_api(test_app: FastAPI) -> None:
    """Verify explicit edge creation and full graph reorganization triggers."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create node A
        r1 = await client.post(
            "/api/memory/graph/nodes",
            json={
                "subject": "auth_policy",
                "predicate": "mfa_required",
                "object_value": "true",
            },
        )
        id_a = r1.json()["node_id"]

        # Create node B
        r2 = await client.post(
            "/api/memory/graph/nodes",
            json={
                "subject": "auth_policy",
                "predicate": "mfa_required",
                "object_value": "false",
            },
        )
        id_b = r2.json()["node_id"]

        # Create manual edge
        edge_resp = await client.post(
            "/api/memory/graph/edges",
            json={
                "source_node_id": id_b,
                "target_node_id": id_a,
                "relation_type": "contradiction",
                "weight": 0.95,
                "rationale": "Directly opposing authentication enforcement policies",
            },
        )
        assert edge_resp.status_code == 201
        edge_data = edge_resp.json()
        assert edge_data["relation_type"] == "contradiction"

        # List edges
        list_edge_resp = await client.get(
            "/api/memory/graph/edges",
            params={"relation_type": "contradiction"},
        )
        assert list_edge_resp.status_code == 200
        assert len(list_edge_resp.json()) == 1

        # Reorganize graph
        reorg_resp = await client.post(
            "/api/memory/graph/reorganize",
            json={"min_confidence": 0.5},
        )
        assert reorg_resp.status_code == 200
        report = reorg_resp.json()
        assert report["analyzed_nodes_count"] >= 2
        assert "batch_id" in report


@pytest.mark.asyncio
async def test_error_handling_api(test_app: FastAPI) -> None:
    """Verify proper 404 HTTP errors for nonexistent entities."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get nonexistent node
        resp = await client.get("/api/memory/graph/nodes/nonexistent_id")
        assert resp.status_code == 404

        # Evolve nonexistent node
        resp = await client.post(
            "/api/memory/graph/nodes/nonexistent_id/evolve",
            json={"object_value": "val", "rationale": "testing"},
        )
        assert resp.status_code == 404

        # Lineage nonexistent node
        resp = await client.get("/api/memory/graph/nodes/nonexistent_id/lineage")
        assert resp.status_code == 404

        # Revert nonexistent node
        resp = await client.post(
            "/api/memory/graph/nodes/any_id/revert",
            json={"historical_node_id": "nonexistent_node", "rationale": "testing"},
        )
        assert resp.status_code == 404
