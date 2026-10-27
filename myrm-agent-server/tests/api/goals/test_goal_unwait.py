"""Ending a goal's wait over HTTP puts the goal back to work, unless a turn already carries it."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.mark.asyncio
async def test_unwait_starts_the_goal_turn(client: TestClient, goal_stream_trigger: AsyncMock):
    session_id = f"test_session_unwait_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "CI Goal")
    await provider.enter_wait(goal.goal_id, reason="GitHub Actions running")

    goal_stream_trigger.assert_not_awaited()

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "unwait"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_awaited_once()
    assert goal_stream_trigger.await_args.args[0] == session_id

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_unwait_leaves_the_goal_to_the_running_turn_when_the_session_is_busy(
    client: TestClient, goal_stream_trigger: AsyncMock
):
    """A message the user sent while the goal waited already has a turn; it carries the goal on."""
    session_id = f"test_session_unwait_busy_{uuid.uuid4().hex}"
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "CI Goal")
    await provider.enter_wait(goal.goal_id, reason="GitHub Actions running")

    with patch("app.services.agent.goals.goal_controls.can_start_goal_turn", return_value=False):
        response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "unwait"})

    assert response.status_code == 200
    assert response.json()["new_status"] == "active"
    goal_stream_trigger.assert_not_awaited()

    GoalRegistry.unregister(session_id)
