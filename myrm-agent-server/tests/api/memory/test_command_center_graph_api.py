"""Unit and contract tests for Memory Command Center Graph Dual-View API.

Verifies:
1. `get_memory_graph` returns `ranked_hubs` sorted by degree and contradiction status.
2. `graph_state` accurately returns 3-states: `storage_disabled`, `empty_knowledge`, `sparse_islands`, and `ready`.
3. Edges are correctly associated with in/out degree counts on hubs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.graph.base import (
    GraphNode,
    GraphRelationship,
    GraphStats,
)

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager


@pytest.fixture
def graph_api_client():
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    manager = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_crud_memory_manager] = lambda: manager
    return TestClient(app), manager


def test_get_memory_graph_storage_disabled(graph_api_client):
    client, manager = graph_api_client
    manager.has_graph = False
    manager._graph = None

    resp = client.get("/api/memory/command-center/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_graph"] is False
    assert data["graph_state"] == "storage_disabled"
    assert data["ranked_hubs"] == []


def test_get_memory_graph_empty_knowledge(graph_api_client):
    client, manager = graph_api_client
    manager.has_graph = True
    graph = AsyncMock()
    graph.get_stats = AsyncMock(
        return_value=GraphStats(node_count=0, relationship_count=0, node_label_counts={}, relationship_type_counts={})
    )
    manager._graph = graph

    resp = client.get("/api/memory/command-center/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_graph"] is True
    assert data["graph_state"] == "empty_knowledge"
    assert data["nodes"] == []
    assert data["edges"] == []


def test_get_memory_graph_sparse_islands_and_ranked_hubs(graph_api_client):
    client, manager = graph_api_client
    manager.has_graph = True
    graph = AsyncMock()
    graph.get_stats = AsyncMock(
        return_value=GraphStats(node_count=3, relationship_count=0, node_label_counts={"Claim": 3}, relationship_type_counts={})
    )
    graph.list_nodes = AsyncMock(
        return_value=[
            GraphNode(id="c1", labels=["Claim"], properties={"content": "Use bun for frontend"}),
            GraphNode(id="c2", labels=["Claim"], properties={"content": "Strict type safety"}),
        ]
    )
    graph.list_relationships = AsyncMock(return_value=[])
    manager._graph = graph

    resp = client.get("/api/memory/command-center/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["graph_state"] == "sparse_islands"
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 0
    assert len(data["ranked_hubs"]) == 2
    assert data["ranked_hubs"][0]["degree"] == 0


def test_get_memory_graph_ready_with_ranked_hubs_and_conflicts(graph_api_client):
    client, manager = graph_api_client
    manager.has_graph = True
    graph = AsyncMock()
    graph.get_stats = AsyncMock(
        return_value=GraphStats(
            node_count=4,
            relationship_count=3,
            node_label_counts={"Claim": 2, "Evidence": 2},
            relationship_type_counts={"SUPPORTED_BY": 2, "CONTRADICTED_BY": 1},
        )
    )
    graph.list_nodes = AsyncMock(
        return_value=[
            GraphNode(id="claim_base", labels=["Claim"], properties={"content": "Primary base rule"}),
            GraphNode(id="claim_conflict", labels=["Claim"], properties={"content": "Old contradictory rule"}),
            GraphNode(id="ev_1", labels=["Evidence"], properties={"quote_snippet": "Proof A"}),
            GraphNode(id="ev_2", labels=["Evidence"], properties={"quote_snippet": "Proof B"}),
        ]
    )
    graph.list_relationships = AsyncMock(
        return_value=[
            GraphRelationship(id="r1", start_id="claim_base", end_id="ev_1", rel_type="SUPPORTED_BY"),
            GraphRelationship(id="r2", start_id="claim_base", end_id="ev_2", rel_type="SUPPORTED_BY"),
            GraphRelationship(id="r3", start_id="claim_conflict", end_id="claim_base", rel_type="CONTRADICTED_BY"),
        ]
    )
    manager._graph = graph

    resp = client.get("/api/memory/command-center/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["graph_state"] == "ready"
    assert len(data["nodes"]) == 4
    assert len(data["edges"]) == 3

    hubs = data["ranked_hubs"]
    assert len(hubs) == 4
    # The conflicted claim should be sorted to the very top priority
    assert hubs[0]["id"] == "claim_conflict"
    assert hubs[0]["has_conflict"] is True
    assert hubs[0]["contradicted_count"] == 1

    # Base rule should have degree = 3 (out=2 to evidences, in=1 from conflict)
    base_hub = next(h for h in hubs if h["id"] == "claim_base")
    assert base_hub["degree"] == 3
    assert base_hub["supported_count"] == 2


def test_get_memory_graph_pushdown_contract(graph_api_client):
    """Verify list_nodes and list_relationships receive pushdown parameters."""
    client, manager = graph_api_client
    manager.has_graph = True
    graph = AsyncMock()
    graph.get_stats = AsyncMock(
        return_value=GraphStats(node_count=2, relationship_count=1, node_label_counts={"Claim": 2}, relationship_type_counts={})
    )
    graph.list_nodes = AsyncMock(
        return_value=[
            GraphNode(id="n1", labels=["Claim"], properties={"primary_namespace": "agent_alpha"}),
            GraphNode(id="n2", labels=["Claim"], properties={"primary_namespace": "agent_alpha"}),
        ]
    )
    graph.list_relationships = AsyncMock(
        return_value=[
            GraphRelationship(id="r1", start_id="n1", end_id="n2", rel_type="SUPPORTS"),
        ]
    )
    manager._graph = graph

    resp = client.get("/api/memory/command-center/graph?namespace=agent_alpha&limit=100")
    assert resp.status_code == 200

    # Verify namespace was passed to list_nodes
    graph.list_nodes.assert_awaited_once_with(limit=100, offset=0, namespace="agent_alpha")

    # Verify node_ids and default temporal parameters were passed to list_relationships
    assert graph.list_relationships.await_count == 1
    call_kwargs = graph.list_relationships.await_args.kwargs
    assert set(call_kwargs.get("node_ids", [])) == {"n1", "n2"}
    assert call_kwargs.get("as_of_time") is None
    assert call_kwargs.get("include_superseded") is False


def test_get_memory_graph_temporal_query(graph_api_client):
    """Verify as_of_time and include_superseded parameters are propagated and edge temporal fields are serialized."""
    client, manager = graph_api_client
    manager.has_graph = True
    graph = AsyncMock()
    graph.get_stats = AsyncMock(
        return_value=GraphStats(node_count=2, relationship_count=1, node_label_counts={"Claim": 2}, relationship_type_counts={})
    )
    graph.list_nodes = AsyncMock(
        return_value=[
            GraphNode(id="n1", labels=["Claim"], properties={"primary_namespace": "agent_alpha"}),
            GraphNode(id="n2", labels=["Claim"], properties={"primary_namespace": "agent_alpha"}),
        ]
    )
    graph.list_relationships = AsyncMock(
        return_value=[
            GraphRelationship(
                id="r_temporal",
                start_id="n1",
                end_id="n2",
                rel_type="CONTRADICTS",
                properties={"weight": 1.0},
                valid_from="2026-08-01T00:00:00Z",
                valid_until="2026-09-01T00:00:00Z",
                superseded_by="r_newer",
                supersedes_id="r_older",
            ),
        ]
    )
    manager._graph = graph

    query_time = "2026-08-15T12:00:00Z"
    resp = client.get(
        f"/api/memory/command-center/graph?namespace=agent_alpha&as_of_time={query_time}&include_superseded=true"
    )
    assert resp.status_code == 200
    data = resp.json()

    # Verify temporal parameters were pushed down to list_relationships
    assert graph.list_relationships.await_count == 1
    call_kwargs = graph.list_relationships.await_args.kwargs
    assert set(call_kwargs.get("node_ids", [])) == {"n1", "n2"}
    assert call_kwargs.get("as_of_time") == query_time
    assert call_kwargs.get("include_superseded") is True


    # Verify edge schema mapping
    edges = data["edges"]
    assert len(edges) == 1
    edge = edges[0]
    assert edge["id"] == "r_temporal"
    assert edge["source"] == "n1"
    assert edge["target"] == "n2"
    assert edge["rel_type"] == "CONTRADICTS"
    assert edge["valid_from"] == "2026-08-01T00:00:00Z"
    assert edge["valid_until"] == "2026-09-01T00:00:00Z"
    assert edge["superseded_by"] == "r_newer"
    assert edge["supersedes_id"] == "r_older"

