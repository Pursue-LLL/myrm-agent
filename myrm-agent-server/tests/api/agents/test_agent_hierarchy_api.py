"""
[POS] tests/api/agents/test_agent_hierarchy_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.agents.agent_hierarchy_router, app.services.agent.agent_hierarchy_service
[OUTPUT] test_register_and_get_provenance_api, test_multi_tier_hierarchy_tree_api, test_cycle_detection_and_breaker_api, test_orphan_agent_promotion_api

Integration test suite for agent creation hierarchy trees, roster listings, and provenance ancestry tracing.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.agent_hierarchy_router import router as agent_hierarchy_router
from app.services.agent.agent_hierarchy_service import (
    AgentHierarchyService,
    get_agent_hierarchy_service,
)


@pytest.fixture
def hierarchy_client() -> Generator[TestClient, None, None]:
    """Provide isolated TestClient fixture mounting agent hierarchy router."""
    service = AgentHierarchyService()

    test_app = FastAPI()
    test_app.include_router(agent_hierarchy_router, prefix="/api/agents")
    test_app.dependency_overrides[get_agent_hierarchy_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_register_and_get_provenance_api(hierarchy_client: TestClient) -> None:
    """Verify registering creation provenance and retrieving origin ancestry."""
    # Register provenance for a root agent
    reg_payload = {
        "agent_id": "root-orchestrator",
        "creator_type": "user",
        "creator_id": "user-admin-01",
        "parent_agent_id": None,
    }
    resp = hierarchy_client.post("/api/agents/hierarchy/provenance", json=reg_payload)
    assert resp.status_code == 201
    prov = resp.json()
    assert prov["agent_id"] == "root-orchestrator"
    assert prov["creator_type"] == "user"
    assert prov["creator_id"] == "user-admin-01"
    assert prov["parent_agent_id"] is None
    assert prov["ancestry_path"] == []

    # Get provenance
    get_resp = hierarchy_client.get("/api/agents/hierarchy/root-orchestrator/provenance")
    assert get_resp.status_code == 200
    assert get_resp.json()["agent_id"] == "root-orchestrator"

    # Query non-existent agent provenance
    missing = hierarchy_client.get("/api/agents/hierarchy/ghost-agent/provenance")
    assert missing.status_code == 404


def test_multi_tier_hierarchy_tree_api(hierarchy_client: TestClient) -> None:
    """Verify multi-tier tree forest construction and ancestry path propagation."""
    # 1. Tier 0 Root
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "lead-architect",
            "creator_type": "user",
            "creator_id": "user-lead",
            "parent_agent_id": None,
        },
    )

    # 2. Tier 1 Children
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "backend-dev",
            "creator_type": "agent",
            "creator_id": "lead-architect",
            "parent_agent_id": "lead-architect",
        },
    )
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "frontend-dev",
            "creator_type": "agent",
            "creator_id": "lead-architect",
            "parent_agent_id": "lead-architect",
        },
    )

    # 3. Tier 2 Grandchild
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "db-worker",
            "creator_type": "agent",
            "creator_id": "backend-dev",
            "parent_agent_id": "backend-dev",
        },
    )

    # Verify grandchild ancestry path
    grandchild_prov = hierarchy_client.get("/api/agents/hierarchy/db-worker/provenance").json()
    assert grandchild_prov["ancestry_path"] == ["lead-architect", "backend-dev"]

    # Verify hierarchy tree structure
    tree_resp = hierarchy_client.get("/api/agents/hierarchy/tree")
    assert tree_resp.status_code == 200
    tree_data = tree_resp.json()
    assert tree_data["total_nodes"] == 4
    assert tree_data["max_depth"] == 2
    assert len(tree_data["roots"]) == 1

    root_node = tree_data["roots"][0]
    assert root_node["agent_id"] == "lead-architect"
    assert root_node["depth"] == 0
    assert len(root_node["children"]) == 2

    # Children order check
    child_ids = [c["agent_id"] for c in root_node["children"]]
    assert "backend-dev" in child_ids
    assert "frontend-dev" in child_ids

    # Backend-dev has db-worker as child
    backend_node = next(c for c in root_node["children"] if c["agent_id"] == "backend-dev")
    assert len(backend_node["children"]) == 1
    assert backend_node["children"][0]["agent_id"] == "db-worker"
    assert backend_node["children"][0]["depth"] == 2


def test_cycle_detection_and_breaker_api(hierarchy_client: TestClient) -> None:
    """Verify circular dependency detection and automatic cycle-severing defense."""
    # Register circular parents: Node A -> Node B -> Node A
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "agent-alpha",
            "creator_type": "agent",
            "creator_id": "agent-beta",
            "parent_agent_id": "agent-beta",
        },
    )
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "agent-beta",
            "creator_type": "agent",
            "creator_id": "agent-alpha",
            "parent_agent_id": "agent-alpha",
        },
    )

    # Fetch tree: must not recurse infinitely, must successfully break cycle
    tree_resp = hierarchy_client.get("/api/agents/hierarchy/tree")
    assert tree_resp.status_code == 200
    data = tree_resp.json()
    assert data["total_nodes"] == 2
    # One of the nodes is severed and promoted to root
    assert len(data["roots"]) >= 1


def test_orphan_agent_promotion_api(hierarchy_client: TestClient) -> None:
    """Verify orphan child with non-existent parent is promoted to top-level root."""
    hierarchy_client.post(
        "/api/agents/hierarchy/provenance",
        json={
            "agent_id": "lonely-worker",
            "creator_type": "script",
            "creator_id": "ci-runner.sh",
            "parent_agent_id": "deleted-or-ghost-parent",
        },
    )

    tree_resp = hierarchy_client.get("/api/agents/hierarchy/tree")
    assert tree_resp.status_code == 200
    data = tree_resp.json()
    assert data["total_nodes"] == 1
    assert len(data["roots"]) == 1
    assert data["roots"][0]["agent_id"] == "lonely-worker"
    assert data["roots"][0]["depth"] == 0
