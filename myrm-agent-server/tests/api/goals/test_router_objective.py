"""Editing the objective of a goal over HTTP: validation, terminal goals and steering of the running turn."""

import uuid

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.mark.asyncio
async def test_update_objective_success(client: TestClient):
    """Test updating the objective of an active goal."""
    session_id = f"test_session_obj_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "Original Objective")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "Updated Objective"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["goal"]["objective"] == "Updated Objective"
    assert data["steered"] is False  # no SteeringToken registered


@pytest.mark.asyncio
async def test_update_objective_empty(client: TestClient):
    """Test that empty objective is rejected."""
    session_id = f"test_session_obj_empty_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "Original")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "   "},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_objective_too_long(client: TestClient):
    """Test that overly long objective is rejected."""
    session_id = f"test_session_obj_long_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "Original")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "x" * 2001},
    )
    assert response.status_code == 400
    assert "2000" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_objective_no_goal(client: TestClient):
    """Test updating objective when no goal exists."""
    session_id = f"test_session_obj_none_{uuid.uuid4().hex}"

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "New Objective"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_objective_terminal_goal(client: TestClient):
    """Test that updating objective on a terminal goal is rejected."""
    session_id = f"test_session_obj_terminal_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    goal = await provider.create_goal(session_id, "Original")
    await provider.update_status(goal.goal_id, GoalStatus.CANCELLED)

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "Cannot update cancelled"},
    )
    assert response.status_code == 400
    assert "terminal" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_objective_with_steering(client: TestClient):
    """Test that steering is injected when a SteeringToken is registered."""
    from unittest.mock import MagicMock

    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.services.agent.steering import SteeringRegistry

    session_id = f"test_session_obj_steer_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "Original")

    mock_token = MagicMock(spec=SteeringToken)
    SteeringRegistry.register(session_id, mock_token)
    try:
        response = client.patch(
            f"/api/v1/goals/{session_id}/objective",
            json={"objective": "Steered Objective"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["steered"] is True
        mock_token.steer.assert_called_once()
        steering_msg = mock_token.steer.call_args[0][0]
        assert "Steered Objective" in steering_msg
        assert "<untrusted_objective>" in steering_msg
    finally:
        SteeringRegistry.unregister(session_id, mock_token)


@pytest.mark.asyncio
async def test_update_objective_unicode(client: TestClient):
    """Test that unicode objectives are handled correctly."""
    session_id = f"test_session_obj_unicode_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "原始目标")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "构建用户管理 REST API，支持中文和日语"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["goal"]["objective"] == "构建用户管理 REST API，支持中文和日语"


@pytest.mark.asyncio
async def test_update_objective_max_boundary(client: TestClient):
    """Test objective at exact max length boundary."""
    session_id = f"test_session_obj_boundary_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "Original")

    # Exactly 2000 chars should succeed
    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "a" * 2000},
    )
    assert response.status_code == 200
