"""
[POS] tests/api/memory/test_memory_crystallization_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.crystallization_router, app.services.memory.memory_crystallization_service
[OUTPUT] test_evaluate_formation_gate_api, test_filter_by_facets_api, test_record_execution_feedback_and_retirement_api, test_get_rule_metrics_api

Unit test suite for Procedural Memory Crystallization Lifecycle and Self-Correction Governor API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.crystallization_router import (
    router as memory_crystallization_router,
)
from app.services.memory.memory_crystallization_service import (
    MemoryCrystallizationService,
    get_memory_crystallization_service,
)


@pytest.fixture
def crystallization_test_client() -> Generator[tuple[TestClient, MemoryCrystallizationService], None, None]:
    """Provide isolated TestClient mounting crystallization router with a clean service instance."""
    service = MemoryCrystallizationService()

    test_app = FastAPI()
    test_app.include_router(memory_crystallization_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_crystallization_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_evaluate_formation_gate_api(
    crystallization_test_client: tuple[TestClient, MemoryCrystallizationService],
) -> None:
    """Verify POST /api/memory/crystallization/evaluate-formation filters trivial noise."""
    client, _ = crystallization_test_client

    # High-signal rule passing threshold
    req_high = {
        "confidence": 0.90,
        "severity": 0.85,
        "content": "Docker 容器通信必须使用自定义 bridge 网络",
    }
    res_high = client.post("/api/memory/crystallization/evaluate-formation", json=req_high)
    assert res_high.status_code == 200
    data_high = res_high.json()
    assert data_high["passed_gate"] is True
    assert data_high["importance"] == 0.765
    assert "approved for crystallization" in data_high["gate_reason"].lower()

    # Low-signal noise failing threshold
    req_low = {
        "confidence": 0.40,
        "severity": 0.50,
        "content": "今天记得喝水",
    }
    res_low = client.post("/api/memory/crystallization/evaluate-formation", json=req_low)
    assert res_low.status_code == 200
    data_low = res_low.json()
    assert data_low["passed_gate"] is False
    assert data_low["importance"] == 0.20
    assert "filtered out" in data_low["gate_reason"].lower()


def test_filter_by_facets_api(
    crystallization_test_client: tuple[TestClient, MemoryCrystallizationService],
) -> None:
    """Verify POST /api/memory/crystallization/filter-facets isolates rules by domain scopes."""
    client, _ = crystallization_test_client

    rules_payload = [
        {
            "rule_id": "rule_devops",
            "facets": ["devops"],
            "success_count": 5,
            "fail_count": 0,
            "win_rate": 1.0,
            "state": "active",
            "weight": 1.0,
            "description": "Devops bridge setting",
        },
        {
            "rule_id": "rule_fe",
            "facets": ["frontend"],
            "success_count": 4,
            "fail_count": 1,
            "win_rate": 0.8,
            "state": "active",
            "weight": 0.8,
            "description": "React query stale time",
        },
        {
            "rule_id": "rule_global",
            "facets": ["global"],
            "success_count": 10,
            "fail_count": 0,
            "win_rate": 1.0,
            "state": "active",
            "weight": 0.95,
            "description": "General git commit requirement",
        },
    ]

    res = client.post(
        "/api/memory/crystallization/filter-facets",
        json={"rules": rules_payload, "active_facets": ["devops"]},
    )
    assert res.status_code == 200
    data = res.json()
    matched_ids = [r["rule_id"] for r in data["matched_rules"]]
    assert "rule_devops" in matched_ids
    assert "rule_global" in matched_ids
    assert "rule_fe" not in matched_ids
    assert data["matched_count"] == 2


def test_record_execution_feedback_and_retirement_api(
    crystallization_test_client: tuple[TestClient, MemoryCrystallizationService],
) -> None:
    """Verify POST /api/memory/crystallization/record-feedback penalizes repeated failures."""
    client, _ = crystallization_test_client

    rule_id = "test_flaky_rule"
    session_id = "sess_001"

    # Turn 1: regular failure
    res1 = client.post(
        "/api/memory/crystallization/record-feedback",
        json={
            "rule_id": rule_id,
            "session_id": session_id,
            "is_success": False,
            "secondary_error_occurred": False,
            "description": "Flaky timeout rule",
        },
    )
    assert res1.status_code == 200
    assert res1.json()["metrics"]["fail_count"] == 1
    assert res1.json()["repeat_failure_penalized"] is False

    # Turn 2: repeat failure in the same session triggers heavier penalty
    res2 = client.post(
        "/api/memory/crystallization/record-feedback",
        json={
            "rule_id": rule_id,
            "session_id": session_id,
            "is_success": False,
            "secondary_error_occurred": True,
        },
    )
    assert res2.status_code == 200
    assert res2.json()["metrics"]["fail_count"] == 3
    assert res2.json()["repeat_failure_penalized"] is True

    # Turn 3: third failure drops win rate to 0.0 and retires the rule
    res3 = client.post(
        "/api/memory/crystallization/record-feedback",
        json={
            "rule_id": rule_id,
            "session_id": session_id,
            "is_success": False,
        },
    )
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["metrics"]["state"] == "retired"
    assert data3["metrics"]["weight"] == 0.0
    assert data3["metrics"]["win_rate"] == 0.0


def test_get_rule_metrics_api(
    crystallization_test_client: tuple[TestClient, MemoryCrystallizationService],
) -> None:
    """Verify GET /api/memory/crystallization/rules/{rule_id}/metrics handles hit and 404."""
    client, _ = crystallization_test_client

    # 404 for non-existent rule
    res_404 = client.get("/api/memory/crystallization/rules/non_existent_rule/metrics")
    assert res_404.status_code == 404

    # Record feedback to register rule
    client.post(
        "/api/memory/crystallization/record-feedback",
        json={
            "rule_id": "registered_rule_99",
            "session_id": "sess_initial",
            "is_success": True,
            "description": "High performance SQL indexing",
        },
    )

    # 200 for existing rule
    res_200 = client.get("/api/memory/crystallization/rules/registered_rule_99/metrics")
    assert res_200.status_code == 200
    data_200 = res_200.json()
    assert data_200["rule_id"] == "registered_rule_99"
    assert data_200["state"] == "active"
    assert data_200["win_rate"] == 1.0
