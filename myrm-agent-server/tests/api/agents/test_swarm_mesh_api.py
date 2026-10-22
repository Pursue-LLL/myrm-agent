"""Unit and API integration tests for SwarmForge Dynamic Topology Orchestrator & Mesh Bus (Item 55).

[INPUT]
- app.api.agents.swarm_mesh_router.router
- app.services.agent.swarm_mesh_service.get_swarm_mesh_service

[OUTPUT]
- Pytest test cases validating declarative topology initialization, dynamic layout switching,
  node scaling, live role migration, P2P mesh bus messaging, and shared blackboard operations.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_swarm_mesh_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.swarm_mesh_router import router as swarm_mesh_router
from app.services.agent.swarm_mesh_service import SwarmMeshService, get_swarm_mesh_service


@pytest.fixture
def service() -> SwarmMeshService:
    """Fixture providing an isolated SwarmMeshService instance."""
    return SwarmMeshService()


@pytest.fixture
def client(service: SwarmMeshService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected SwarmMeshService dependency override."""
    app = FastAPI()
    app.include_router(swarm_mesh_router)
    app.dependency_overrides[get_swarm_mesh_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_topology_state_default(client: TestClient) -> None:
    """Verify fetching initial active topology state returns default nodes and edges."""
    response = client.get("/agents/swarm-mesh/topology")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["topology_type"] in ["star", "hierarchical_tree", "peer_mesh", "pipeline", "ring"]
    assert len(data["nodes"]) >= 4
    assert len(data["edges"]) >= 3


def test_create_topology(client: TestClient) -> None:
    """Verify creating a new topology instance with PEER_MESH layout."""
    payload = {
        "topology_type": "peer_mesh",
        "max_nodes": 12,
        "is_adaptive": True,
    }
    response = client.post("/agents/swarm-mesh/create", json=payload)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["topology_type"] == "peer_mesh"
    # 4 default nodes in full mesh -> 6 edges
    assert len(data["edges"]) == 6


def test_switch_topology(client: TestClient) -> None:
    """Verify dynamic runtime layout switching to PIPELINE while keeping nodes intact."""
    payload = {"target_type": "pipeline"}
    response = client.post("/agents/swarm-mesh/switch", json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["topology_type"] == "pipeline"
    assert len(data["nodes"]) >= 4
    assert len(data["edges"]) == len(data["nodes"]) - 1


def test_scale_nodes_out_and_in(client: TestClient) -> None:
    """Verify elastically scaling out a new node and scaling in."""
    new_node = {
        "node_id": "agent-scale-01",
        "name": "Dynamic Worker 01",
        "role": "worker",
        "status": "active",
        "capabilities": ["task_executor"],
        "connected_peers": [],
        "workload_score": 0.0,
        "meta": {},
    }
    # Scale out
    res_out = client.post(
        "/agents/swarm-mesh/scale",
        json={"action": "scale_out", "node": new_node},
    )
    assert res_out.status_code == 200
    nodes_out = res_out.json()["data"]["nodes"]
    assert "agent-scale-01" in nodes_out

    # Scale in
    res_in = client.post(
        "/agents/swarm-mesh/scale",
        json={"action": "scale_in", "node": new_node},
    )
    assert res_in.status_code == 200
    nodes_in = res_in.json()["data"]["nodes"]
    assert "agent-scale-01" not in nodes_in


def test_migrate_node(client: TestClient) -> None:
    """Verify live node role migration with metadata state persistence."""
    req = {
        "node_id": "agent-worker-01",
        "target_role": "reviewer",
        "state_diff": {"migration_tag": "promoted_qa"},
        "reason": "Elevated to security reviewer",
    }
    res = client.post("/agents/swarm-mesh/migrate", json=req)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["success"] is True
    assert data["previous_role"] == "worker"
    assert data["current_role"] == "reviewer"


def test_send_mesh_message(client: TestClient) -> None:
    """Verify dispatching a message over the P2P mesh bus."""
    msg_payload = {
        "sender_id": "agent-coordinator-01",
        "recipient_id": "*",
        "routing_mode": "broadcast",
        "channel": "system_announcement",
        "payload": {"version": 1, "status": "all_green"},
    }
    res = client.post("/agents/swarm-mesh/messages", json=msg_payload)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["sender_id"] == "agent-coordinator-01"
    assert data["routing_mode"] == "broadcast"


def test_blackboard_write_and_read(client: TestClient) -> None:
    """Verify writing facts to the shared blackboard and reading them back."""
    write_req = {
        "key": "cluster.leader",
        "value": "agent-coordinator-01",
        "author_id": "agent-coordinator-01",
        "tags": ["consensus", "leader"],
    }
    res_write = client.post("/agents/swarm-mesh/blackboard", json=write_req)
    assert res_write.status_code == 201
    entry = res_write.json()["data"]
    assert entry["key"] == "cluster.leader"
    assert entry["version"] >= 1

    # Read back specific key
    res_read = client.get("/agents/swarm-mesh/blackboard?key=cluster.leader")
    assert res_read.status_code == 200
    read_data = res_read.json()["data"]
    assert "cluster.leader" in read_data
    assert read_data["cluster.leader"]["value"] == "agent-coordinator-01"
