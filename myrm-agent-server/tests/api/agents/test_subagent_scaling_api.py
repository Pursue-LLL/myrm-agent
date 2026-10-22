"""Unit tests for Subagent Concurrency & Tool Budget Adaptive Scaling API endpoints.

[INPUT]
- app.api.agents.subagent_scaling_router.router
- app.services.agent.subagent_scaling_service.SubagentScalingService

[OUTPUT]
- Pytest cases verifying zero-disruption configuration migration,
  80% dynamic watermark heartbeats, debounced alerts, dismiss, expand, and cleanup.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_subagent_scaling_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.subagent_scaling_router import (
    get_subagent_scaling_service,
)
from app.api.agents.subagent_scaling_router import (
    router as subagent_scaling_router,
)
from app.services.agent.subagent_scaling_service import SubagentScalingService


@pytest.fixture
def scaling_service() -> SubagentScalingService:
    return SubagentScalingService()


@pytest.fixture
def scaling_client(
    scaling_service: SubagentScalingService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(subagent_scaling_router)
    app.dependency_overrides[get_subagent_scaling_service] = lambda: scaling_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_migrate_config_endpoint(scaling_client: TestClient) -> None:
    # 1. Legacy defaults: concurrency 3, max_turns 50 -> migrated to 10 and 250
    legacy_payload = {
        "concurrency_limit": 3,
        "max_turns": 50,
        "extra_config": {"model": "deepseek-coder"},
    }
    resp = scaling_client.post("/subagents/scaling/migrate-config", json=legacy_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["migrated"] is True
    assert data["old_concurrency"] == 3
    assert data["new_concurrency"] == 10
    assert data["old_max_turns"] == 50
    assert data["new_max_turns"] == 250
    assert data["concurrency_migrated"] is True
    assert data["max_turns_migrated"] is True
    assert data["final_config"]["concurrency_limit"] == 10
    assert data["final_config"]["max_turns"] == 250
    assert data["final_config"]["model"] == "deepseek-coder"

    # 2. Customized config: concurrency 8, max_turns 120 -> 100% preserved
    custom_payload = {
        "concurrency_limit": 8,
        "max_turns": 120,
    }
    resp_custom = scaling_client.post("/subagents/scaling/migrate-config", json=custom_payload)
    assert resp_custom.status_code == 200
    custom_data = resp_custom.json()["data"]
    assert custom_data["migrated"] is False
    assert custom_data["new_concurrency"] == 8
    assert custom_data["new_max_turns"] == 120


def test_watermark_heartbeat_and_alerts_api(scaling_client: TestClient) -> None:
    session_id = "session_scaling_test_01"
    subagent_id = "sub_worker_alpha"

    # 1. Below 80% watermark: 100/250 (40%) -> no alert
    heartbeat_1 = {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "subagent_name": "AlphaWorker",
        "current_turn": 100,
        "max_turns": 250,
    }
    resp1 = scaling_client.post("/subagents/scaling/watermark-heartbeat", json=heartbeat_1)
    assert resp1.status_code == 200
    d1 = resp1.json()["data"]
    assert d1["is_alert_triggered"] is False
    assert d1["usage_ratio"] == 0.4
    assert d1["turns_remaining"] == 150

    # 2. Cross 80% watermark: 200/250 (80%) -> alert triggered
    heartbeat_2 = {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "subagent_name": "AlphaWorker",
        "current_turn": 200,
        "max_turns": 250,
    }
    resp2 = scaling_client.post("/subagents/scaling/watermark-heartbeat", json=heartbeat_2)
    assert resp2.status_code == 200
    d2 = resp2.json()["data"]
    assert d2["is_alert_triggered"] is True
    assert d2["usage_ratio"] == 0.8
    assert d2["turns_remaining"] == 50
    assert "reached 80.0% of turn budget" in d2["alert_message"]

    # 3. Subsequent turn: 201/250 -> debounced (no duplicate alert)
    heartbeat_3 = {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "subagent_name": "AlphaWorker",
        "current_turn": 201,
        "max_turns": 250,
    }
    resp3 = scaling_client.post("/subagents/scaling/watermark-heartbeat", json=heartbeat_3)
    assert resp3.status_code == 200
    assert resp3.json()["data"]["is_alert_triggered"] is False

    # 4. List recorded alerts
    resp_alerts = scaling_client.get(f"/subagents/scaling/sessions/{session_id}/watermark-alerts")
    assert resp_alerts.status_code == 200
    alerts_data = resp_alerts.json()["data"]
    assert alerts_data["count"] == 1
    assert alerts_data["alerts"][0]["subagent_id"] == subagent_id
    assert alerts_data["alerts"][0]["status"] == "active"


def test_watermark_dismiss_expand_and_cleanup_api(scaling_client: TestClient) -> None:
    session_id = "session_scaling_test_02"
    subagent_id = "sub_worker_beta"

    # Trigger alert
    scaling_client.post(
        "/subagents/scaling/watermark-heartbeat",
        json={
            "session_id": session_id,
            "subagent_id": subagent_id,
            "subagent_name": "BetaWorker",
            "current_turn": 205,
            "max_turns": 250,
        },
    )

    # 1. Dismiss alert
    resp_dismiss = scaling_client.post(
        f"/subagents/scaling/sessions/{session_id}/watermark-alerts/{subagent_id}/dismiss"
    )
    assert resp_dismiss.status_code == 200
    assert resp_dismiss.json()["data"]["dismissed"] is True

    # 2. Expand budget
    resp_expand = scaling_client.post(
        f"/subagents/scaling/sessions/{session_id}/watermark-alerts/{subagent_id}/expand"
    )
    assert resp_expand.status_code == 200
    assert resp_expand.json()["data"]["expanded"] is True

    # 3. Cleanup session
    resp_clean = scaling_client.delete(
        f"/subagents/scaling/sessions/{session_id}/watermark-alerts"
    )
    assert resp_clean.status_code == 200
    assert resp_clean.json()["data"]["cleaned"] is True

    # 4. Verify empty after cleanup
    resp_empty = scaling_client.get(
        f"/subagents/scaling/sessions/{session_id}/watermark-alerts"
    )
    assert resp_empty.status_code == 200
    assert resp_empty.json()["data"]["count"] == 0
