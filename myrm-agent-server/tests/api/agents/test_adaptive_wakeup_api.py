"""Unit tests for Adaptive Wakeup API endpoints and service coordination (Item 29).

[INPUT]
- app.api.agents.adaptive_wakeup_router.router
- app.services.agent.adaptive_wakeup.service.AdaptiveWakeupService

[OUTPUT]
- Pytest cases verifying budget monitoring, human turn reset, user stop suppression,
  busy host injection, and budget-exhaustion degradation.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_adaptive_wakeup_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.coordination.adaptive_wakeup import HostActivityState
from starlette.testclient import TestClient

from app.api.agents.adaptive_wakeup_router import router as adaptive_wakeup_router
from app.services.agent.adaptive_wakeup.service import (
    AdaptiveWakeupService,
    get_adaptive_wakeup_service,
)


@pytest.fixture
def mock_wakeup_service() -> AdaptiveWakeupService:
    """Fixture providing a fresh isolated AdaptiveWakeupService."""
    return AdaptiveWakeupService(default_max_consecutive_wakes=3)


@pytest.fixture
def wakeup_client(
    mock_wakeup_service: AdaptiveWakeupService,
) -> Generator[TestClient, None, None]:
    """TestClient wired with isolated AdaptiveWakeupService dependency override."""
    app = FastAPI()
    app.include_router(adaptive_wakeup_router, prefix="/agents")
    app.dependency_overrides[get_adaptive_wakeup_service] = lambda: mock_wakeup_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_budget_initial_state_and_human_reset(
    wakeup_client: TestClient,
    mock_wakeup_service: AdaptiveWakeupService,
) -> None:
    session_id = "test-api-session-budget"

    # 1. Check initial state
    resp = wakeup_client.get(f"/agents/adaptive-wakeup/sessions/{session_id}/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["consecutive_wakes"] == 0
    assert data["max_consecutive_wakes"] == 3
    assert data["budget_remaining"] == 3
    assert data["is_exhausted"] is False
    assert data["host_activity"] == "idle"

    # 2. Trigger settlements to consume budget
    for i in range(1, 4):
        post_resp = wakeup_client.post(
            f"/agents/adaptive-wakeup/sessions/{session_id}/settlements",
            json={
                "source_type": "background_job",
                "source_id": f"job-{i}",
                "success": True,
                "summary": f"Job {i} completed",
            },
        )
        assert post_resp.status_code == 200
        decision = post_resp.json()
        assert decision["channel"] == "followup"
        assert decision["consecutive_wakes"] == i

    # 4th settlement should be DEGRADE
    degrade_resp = wakeup_client.post(
        f"/agents/adaptive-wakeup/sessions/{session_id}/settlements",
        json={
            "source_type": "subagent",
            "source_id": "sub-overflow",
            "success": True,
            "summary": "Subagent overflow completed",
        },
    )
    assert degrade_resp.status_code == 200
    degrade_data = degrade_resp.json()
    assert degrade_data["channel"] == "degrade"
    assert degrade_data["budget_remaining"] == 0

    # 3. Simulate human message turn to reset budget
    reset_resp = wakeup_client.post(
        f"/agents/adaptive-wakeup/sessions/{session_id}/human-turn"
    )
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["consecutive_wakes"] == 0
    assert reset_data["budget_remaining"] == 3
    assert reset_data["is_exhausted"] is False


def test_user_stop_suppression_endpoint(
    wakeup_client: TestClient,
    mock_wakeup_service: AdaptiveWakeupService,
) -> None:
    session_id = "test-api-session-stop"

    # Notify user stop
    stop_resp = wakeup_client.post(f"/agents/adaptive-wakeup/sessions/{session_id}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["is_user_stopped"] is True

    # Subsequent settlement should be SUPPRESS
    post_resp = wakeup_client.post(
        f"/agents/adaptive-wakeup/sessions/{session_id}/settlements",
        json={
            "source_type": "subagent",
            "source_id": "sub-stop-1",
            "success": True,
            "summary": "Should be suppressed",
        },
    )
    assert post_resp.status_code == 200
    decision = post_resp.json()
    assert decision["channel"] == "suppress"
    assert "suppressed" in decision["reason"].lower()


def test_busy_host_injection_and_drain(
    wakeup_client: TestClient,
    mock_wakeup_service: AdaptiveWakeupService,
) -> None:
    session_id = "test-api-session-busy"
    mock_wakeup_service.set_host_activity(session_id, HostActivityState.BUSY)

    # Post settlement while host is BUSY -> channel should be INJECT
    post_resp = wakeup_client.post(
        f"/agents/adaptive-wakeup/sessions/{session_id}/settlements",
        json={
            "source_type": "background_job",
            "source_id": "job-busy-101",
            "success": True,
            "summary": "Compile done during generation",
        },
    )
    assert post_resp.status_code == 200
    decision = post_resp.json()
    assert decision["channel"] == "inject"

    # Query injected events without draining
    peek_resp = wakeup_client.get(
        f"/agents/adaptive-wakeup/sessions/{session_id}/injected?drain=false"
    )
    assert peek_resp.status_code == 200
    peek_data = peek_resp.json()
    assert peek_data["count"] == 1
    assert peek_data["events"][0]["source_id"] == "job-busy-101"

    # Query with drain=true
    drain_resp = wakeup_client.get(
        f"/agents/adaptive-wakeup/sessions/{session_id}/injected?drain=true"
    )
    assert drain_resp.status_code == 200
    assert drain_resp.json()["count"] == 1

    # Verify inbox is now empty
    empty_resp = wakeup_client.get(
        f"/agents/adaptive-wakeup/sessions/{session_id}/injected"
    )
    assert empty_resp.status_code == 200
    assert empty_resp.json()["count"] == 0
