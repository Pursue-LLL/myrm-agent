"""Unit tests for Graph Memory Reorganization and Lineage Traceability endpoints.

[POS]
Server 端图谱重组与演化溯源 API 测试套件。
验证 /api/memory/lineage/ 下各端点的状态码、数据契约、白盒 DAG 追溯与版本回退闭环。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.api.memory.memory_lineage_router import router as memory_lineage_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting memory lineage router."""
    api_app = FastAPI()
    api_app.include_router(memory_lineage_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_get_lineage_stats(test_app: FastAPI) -> None:
    """Test retrieving lineage overview metrics."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/memory/lineage/stats")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_nodes" in data
        assert "active_nodes" in data
        assert "superseded_nodes" in data
        assert "total_edges" in data
        assert data["total_nodes"] >= 2
        assert data["active_nodes"] >= 1


@pytest.mark.asyncio
async def test_get_graph_topology(test_app: FastAPI) -> None:
    """Test retrieving graph topology for DAG visualization."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/memory/lineage/topology")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert len(data["nodes"]) >= 2


@pytest.mark.asyncio
async def test_trigger_reorganization_pass(test_app: FastAPI) -> None:
    """Test triggering automated graph reorganization pass."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"min_confidence": 0.5}
        response = await client.post("/api/memory/lineage/reorganize", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "batch_id" in data
        assert "analyzed_nodes_count" in data
        assert "created_edges_count" in data
        assert isinstance(data["edges"], list)


@pytest.mark.asyncio
async def test_trace_node_lineage_dag(test_app: FastAPI) -> None:
    """Test white-box lineage DAG tracing for an evolved memory node."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        target_node_id = "mem_pref_coffee_v2"
        response = await client.get(f"/api/memory/lineage/trace/{target_node_id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["target_node"]["node_id"] == target_node_id
        assert data["is_latest"] is True
        assert "ancestor_nodes" in data
        assert len(data["ancestor_nodes"]) >= 1
        ancestor_ids = [n["node_id"] for n in data["ancestor_nodes"]]
        assert "mem_pref_coffee_v1" in ancestor_ids
        assert len(data["steps"]) >= 1


@pytest.mark.asyncio
async def test_revert_historical_version(test_app: FastAPI) -> None:
    """Test rolling back an active memory slot to a historical version snapshot."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "historical_node_id": "mem_pref_coffee_v1",
            "rationale": "Rollback to black coffee per user request",
        }
        response = await client.post("/api/memory/lineage/revert", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "reverted_node" in data
        assert "restored_active_node" in data
        restored = data["restored_active_node"]
        assert restored["status"] == "active"
        assert restored["object_value"] == "Black Americano"
        assert restored["version"] >= 3
