"""Goals that wait for a provider usage limit: status payload, "retry now" and pause."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.usage_limit_resume import ResumeResult


@pytest.mark.asyncio
async def test_status_exposes_the_usage_limit_hold_for_the_goal_panel(client: TestClient):
    """The Goal panel renders the resume time from ``metadata.wait_kind`` / ``wait_resume_at``."""
    session_id = f"test_session_usage_limit_status_{uuid.uuid4().hex}"
    resume_at = datetime.now(UTC) + timedelta(hours=2)
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Long job")
    await provider.enter_wait(goal.goal_id, reason="limit", kind="usage_limit", resume_at=resume_at)

    response = client.get(f"/api/v1/goals/{session_id}/status")

    assert response.status_code == 200
    data = response.json()["goal"]
    assert data["status"] == "wait"
    assert data["metadata"]["wait_kind"] == "usage_limit"
    assert data["metadata"]["wait_resume_at"] == resume_at.isoformat()

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [("RESUMED", 200), ("BUSY", 409), ("NOT_WAITING", 409)],
)
async def test_unwait_on_usage_limit_wait_resumes_through_the_wake_path(client: TestClient, outcome, expected_status):
    """'Retry now' on a usage-limit wait must start the turn, not just flip the status."""
    session_id = f"test_session_usage_limit_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Long job")
    await provider.enter_wait(goal.goal_id, reason="limit", kind="usage_limit")

    with patch(
        "app.services.agent.goals.usage_limit_resume.resume_goal_after_usage_limit",
        new_callable=AsyncMock,
        return_value=ResumeResult[outcome],
    ) as resume:
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "unwait"})

    resume.assert_awaited_once_with(session_id)
    assert response.status_code == expected_status

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_pause_keeps_a_goal_that_waits_for_a_usage_limit_and_resume_clears_the_hold(client: TestClient):
    """Pause stops the automatic wake-up without cancelling; resuming later drops the stale hold."""
    session_id = f"test_session_usage_limit_pause_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Long job")
    await provider.enter_wait(goal.goal_id, reason="limit", kind="usage_limit", resume_at=datetime.now(UTC) + timedelta(hours=2))

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause", "note": "Need my quota this morning"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "paused"
    paused = client.get(f"/api/v1/goals/{session_id}/status").json()["goal"]
    assert paused["status"] == "paused"
    assert paused["reason"] == "Need my quota this morning"

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    resumed = client.get(f"/api/v1/goals/{session_id}/status").json()["goal"]
    assert "wait_kind" not in resumed["metadata"]
    assert "wait_resume_at" not in resumed["metadata"]

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_pause_still_requires_an_active_or_waiting_goal(client: TestClient):
    """A goal that is already paused is not pausable again."""
    session_id = f"test_session_pause_twice_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Once")

    assert client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"}).status_code == 200
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})

    assert response.status_code == 404

    GoalRegistry.unregister(session_id)
