"""
[POS] tests/api/memory/test_hindsight_reflection_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.hindsight_reflection_router
[OUTPUT] test_reflect_task_failure_api, test_get_pre_execution_warnings_api, test_list_rules_and_stats_api
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.hindsight_reflection_router import (
    router as hindsight_reflection_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting hindsight reflection router."""
    test_app = FastAPI()
    test_app.include_router(hindsight_reflection_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_reflect_task_failure_api(client: TestClient) -> None:
    """Verify POST /api/memory/hindsight/reflect endpoint."""
    payload = {
        "trajectory": {
            "task_id": "failed-job-901",
            "task_goal": "Compile and install system packages via bash",
            "turns": [
                {
                    "turn_index": 1,
                    "tool_name": "bash",
                    "tool_input": {"command": "apt-get install -y nginx"},
                    "tool_output": "E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)",
                    "error_message": "Permission denied: unable to acquire dpkg lock",
                }
            ],
            "terminal_error": "Installation failed with exit code 100",
        },
        "max_turns": 5,
    }

    resp = client.post("/api/memory/hindsight/reflect", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    rule = body["rule"]
    assert "rule_id" in rule
    assert "[bash]" in rule["task_pattern"]
    assert "permission" in rule["tags"]
    assert rule["confidence"] >= 0.8
    assert "check file permissions" in rule["correction_advice"].lower()


def test_get_pre_execution_warnings_api(client: TestClient) -> None:
    """Verify POST /api/memory/hindsight/warnings matches historical pitfalls."""
    # First record a failure rule
    client.post(
        "/api/memory/hindsight/reflect",
        json={
            "trajectory": {
                "task_id": "failed-init-902",
                "task_goal": "Setup database migrations with postgres",
                "turns": [
                    {
                        "turn_index": 1,
                        "tool_name": "db_client",
                        "tool_input": {"action": "migrate"},
                        "tool_output": "FATAL: password authentication failed for user 'admin'",
                        "error_message": "401 Unauthorized database access",
                    }
                ],
                "terminal_error": "Migration aborted due to bad credentials",
            },
            "max_turns": 5,
        },
    )

    # Query proactive pre-execution warnings for upcoming similar task
    query_payload = {
        "task_goal": "Setup and migrate database schemas with postgres",
        "intended_tools": ["db_client"],
        "top_k": 2,
    }

    resp = client.post("/api/memory/hindsight/warnings", json=query_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_warnings"] >= 1
    w = data["warnings"][0]
    assert "Historical Pitfall" in w["warning_text"]
    assert "Recommended Pre-Action" in w["recommended_action"]


def test_list_rules_and_stats_api(client: TestClient) -> None:
    """Verify GET /rules and GET /stats endpoints."""
    # 1. Fetch rules list
    rules_resp = client.get("/api/memory/hindsight/rules")
    assert rules_resp.status_code == 200
    rules = rules_resp.json()
    assert isinstance(rules, list)

    # 2. Fetch buffer stats
    stats_resp = client.get("/api/memory/hindsight/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_rules" in stats
    assert "avg_confidence" in stats
    assert "total_hits" in stats
