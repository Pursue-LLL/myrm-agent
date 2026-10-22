"""Unit tests for Model-Tier Adaptive Topology Pruning REST API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.agents.topology_pruning_router

[OUTPUT]
- Pytest test cases validating model tier catalog discovery and pruning evaluation endpoints.

[POS]
tests/api/agents/test_topology_pruning_api.py: API test suite for Item 8 ModelTierAdaptiveTopologyPruning.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.topology_pruning_router import router as topology_pruning_router


@pytest.fixture
def pruning_client() -> TestClient:
    """Create test client mounting topology_pruning_router."""
    app = FastAPI()
    app.include_router(topology_pruning_router, prefix="/api/v1")
    return TestClient(app)


def test_get_model_tier_catalog_api(pruning_client: TestClient) -> None:
    """Verify GET /api/v1/agents/topology/tiers returns intelligence hierarchy catalog."""
    response = pruning_client.get("/api/v1/agents/topology/tiers")
    assert response.status_code == 200
    data = response.json()

    assert "tiers" in data
    assert data["total_tiers"] >= 3

    tier_names = {t["tier"] for t in data["tiers"]}
    assert "tier_1_sota_reasoning" in tier_names
    assert "tier_2_strong_base" in tier_names
    assert "tier_3_fast_light" in tier_names

    tier_1_entry = next(t for t in data["tiers"] if t["tier"] == "tier_1_sota_reasoning")
    assert "claude-3-7-sonnet" in tier_1_entry["representative_models"]
    assert "deepseek-r1" in tier_1_entry["representative_models"]


def test_evaluate_topology_pruning_tier_1_folding_api(
    pruning_client: TestClient,
) -> None:
    """Verify POST /api/v1/agents/topology/prune-evaluation folds medium task for Tier 1 model."""
    payload = {
        "task_description": "Refactor database connection pool and add retry interceptor",
        "model_name": "claude-3-7-sonnet",
        "planned_subtasks_count": 3,
        "strategy": "auto",
    }
    response = pruning_client.post("/api/v1/agents/topology/prune-evaluation", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["decision"] == "direct_execution"
    assert data["is_folded"] is True
    assert data["model_tier"] == "tier_1_sota_reasoning"
    assert data["executed_subtasks_count"] == 1
    assert data["estimated_saved_turns"] == 6
    assert data["estimated_saved_tokens"] == 4800
    assert "Tier 1 SOTA model" in data["rationale"]


def test_evaluate_topology_pruning_tier_3_fanout_api(
    pruning_client: TestClient,
) -> None:
    """Verify POST /api/v1/agents/topology/prune-evaluation preserves multi-agent for Tier 3 model."""
    payload = {
        "task_description": "Refactor database connection pool and add retry interceptor",
        "model_name": "qwen-2.5-7b",
        "planned_subtasks_count": 3,
        "strategy": "auto",
    }
    response = pruning_client.post("/api/v1/agents/topology/prune-evaluation", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["decision"] == "fanout_multi_agent"
    assert data["is_folded"] is False
    assert data["model_tier"] == "tier_3_fast_light"
    assert data["executed_subtasks_count"] == 3
    assert data["estimated_saved_turns"] == 0


def test_evaluate_topology_pruning_user_override_api(
    pruning_client: TestClient,
) -> None:
    """Verify strategy override is strictly respected by evaluation API."""
    # Force always_multi_agent on Tier 1 model
    p1 = {
        "task_description": "Small bugfix in logging handler",
        "model_name": "claude-3-7-sonnet",
        "planned_subtasks_count": 3,
        "strategy": "always_multi_agent",
    }
    res1 = pruning_client.post("/api/v1/agents/topology/prune-evaluation", json=p1)
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["decision"] == "fanout_multi_agent"
    assert d1["is_folded"] is False

    # Force direct_only on Tier 3 model
    p2 = {
        "task_description": "Complex distributed transaction orchestrator",
        "model_name": "qwen-2.5-7b",
        "planned_subtasks_count": 4,
        "strategy": "direct_only",
    }
    res2 = pruning_client.post("/api/v1/agents/topology/prune-evaluation", json=p2)
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["decision"] == "direct_execution"
    assert d2["is_folded"] is True
