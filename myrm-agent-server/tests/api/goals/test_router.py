import uuid

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.goal_registry import GoalRegistry


@pytest.fixture
def client():
    # To avoid importing app.main which has other dependencies, we just create a simple app with the router
    from fastapi import FastAPI

    from app.api.goals.router import router as goals_router

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")

    # Mock get_storage_provider to avoid DB issues in tests
    from unittest.mock import patch

    from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend("/tmp/test_storage")):
        with patch("app.api.goals.router.get_features") as mock_features:
            mock_features.return_value.get_bool.return_value = True
            with TestClient(app) as client:
                yield client


@pytest.mark.asyncio
async def test_get_goal_status_none(client: TestClient):
    """Test getting goal status when no goal exists."""
    session_id = "test_session_none"

    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.status_code == 200
    assert response.json() == {"goal": None}


@pytest.mark.asyncio
async def test_goal_status_lifecycle(client: TestClient):
    """Test the full lifecycle of a goal via API."""
    session_id = f"test_session_lifecycle_{uuid.uuid4().hex}"

    # 1. Create a goal provider and a goal manually (simulating agent stream start)
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Test API Goal")

    # 2. Get status
    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["goal"] is not None
    assert data["goal"]["goal_id"] == goal.goal_id
    assert data["goal"]["status"] == "active"

    # 3. Pause goal
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "paused"

    # Verify via get
    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.json()["goal"]["status"] == "paused"

    # 4. Resume goal
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "active"

    # 5. Cancel goal
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "cancel"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "cancelled"

    # 6. Approve goal (force complete)
    # First, make it active again (just for testing logic, since cancelled is terminal in theory)
    # Wait, let's create a new goal for approve/reject testing
    GoalRegistry.unregister(session_id)

    provider = GoalRegistry.get_or_create_provider(session_id)
    goal2 = await provider.create_goal(session_id, "Test Approve/Reject Goal")

    # Needs human review status usually set by agent
    await provider.update_status(goal2.goal_id, GoalStatus.NEEDS_HUMAN_REVIEW)

    # Reject
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "reject"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "active"

    # Approve
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "approve"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "complete"

    # Cleanup
    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_status_invalid_action(client: TestClient):
    """Test updating status with invalid action."""
    session_id = f"test_session_invalid_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)

    # Check if goal already exists from previous test run
    goal = await provider.get_active_goal(session_id)
    if not goal:
        goal = await provider.create_goal(session_id, "Test API Goal")

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "invalid_action"})
    assert response.status_code == 400
    assert "Invalid action" in response.json()["detail"]

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_status_no_active_goal(client: TestClient):
    """Test updating status when no active goal exists."""
    session_id = f"test_session_no_active_{uuid.uuid4().hex}"

    # Create provider but no goal
    GoalRegistry.get_or_create_provider(session_id)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})
    assert response.status_code == 404
    assert "No active goal found" in response.json()["detail"]

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_subgoal_api(client: TestClient):
    """Test the subgoal management API endpoints."""
    session_id = f"test_session_subgoals_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Test Subgoal API Goal")

    # 1. Add subgoal
    response = client.post(f"/api/v1/goals/{session_id}/subgoals", json={"text": "First Subgoal"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["subgoal"]["text"] == "First Subgoal"

    # 2. Add another subgoal
    response = client.post(f"/api/v1/goals/{session_id}/subgoals", json={"text": "Second Subgoal"})
    assert response.status_code == 200

    # 3. Remove subgoal
    response = client.delete(f"/api/v1/goals/{session_id}/subgoals/0")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["removed"]["text"] == "First Subgoal"

    # Verify removal invalid index
    response = client.delete(f"/api/v1/goals/{session_id}/subgoals/5")
    assert response.status_code == 404

    # 4. Clear subgoals
    response = client.delete(f"/api/v1/goals/{session_id}/subgoals")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["cleared_count"] == 1

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_goal_queue_api(client: TestClient):
    """Test the queue management API: list, cancel, reorder."""
    session_id = f"test_session_queue_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)

    active = await provider.create_goal(session_id, "Active Goal")
    assert active.status.value == "active"

    q1 = await provider.create_goal(session_id, "Queued Goal 1")
    q2 = await provider.create_goal(session_id, "Queued Goal 2")
    assert q1.status.value == "queued"
    assert q2.status.value == "queued"

    # GET queue
    response = client.get(f"/api/v1/goals/{session_id}/queue")
    assert response.status_code == 200
    data = response.json()
    assert len(data["queue"]) == 2
    assert data["queue"][0]["objective"] == "Queued Goal 1"

    # Reorder: put q2 first
    response = client.post(
        f"/api/v1/goals/{session_id}/queue/reorder",
        json={"ordered_goal_ids": [q2.goal_id, q1.goal_id]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify reorder
    response = client.get(f"/api/v1/goals/{session_id}/queue")
    queue = response.json()["queue"]
    assert queue[0]["objective"] == "Queued Goal 2"
    assert queue[1]["objective"] == "Queued Goal 1"

    # Cancel q1
    response = client.delete(f"/api/v1/goals/{session_id}/queue/{q1.goal_id}")
    assert response.status_code == 200
    assert response.json()["goal_id"] == q1.goal_id

    # Verify only q2 remains
    response = client.get(f"/api/v1/goals/{session_id}/queue")
    queue = response.json()["queue"]
    assert len(queue) == 1
    assert queue[0]["goal_id"] == q2.goal_id

    # Cancel non-existent
    response = client.delete(f"/api/v1/goals/{session_id}/queue/fake-id")
    assert response.status_code == 404

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_success(client: TestClient):
    """Test updating the objective of an active goal."""
    session_id = f"test_session_obj_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
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

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_empty(client: TestClient):
    """Test that empty objective is rejected."""
    session_id = f"test_session_obj_empty_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Original")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "   "},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_too_long(client: TestClient):
    """Test that overly long objective is rejected."""
    session_id = f"test_session_obj_long_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Original")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "x" * 2001},
    )
    assert response.status_code == 400
    assert "2000" in response.json()["detail"]

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_no_goal(client: TestClient):
    """Test updating objective when no goal exists."""
    session_id = f"test_session_obj_none_{uuid.uuid4().hex}"

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "New Objective"},
    )
    assert response.status_code == 404

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_terminal_goal(client: TestClient):
    """Test that updating objective on a terminal goal is rejected."""
    session_id = f"test_session_obj_terminal_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Original")
    await provider.update_status(goal.goal_id, GoalStatus.CANCELLED)

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "Cannot update cancelled"},
    )
    assert response.status_code == 400
    assert "terminal" in response.json()["detail"].lower()

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_with_steering(client: TestClient):
    """Test that steering is injected when a SteeringToken is registered."""
    from unittest.mock import MagicMock

    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.services.agent.steering_registry import SteeringRegistry

    session_id = f"test_session_obj_steer_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
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
        SteeringRegistry.unregister(session_id)
        GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_unicode(client: TestClient):
    """Test that unicode objectives are handled correctly."""
    session_id = f"test_session_obj_unicode_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "原始目标")

    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "构建用户管理 REST API，支持中文和日语"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["goal"]["objective"] == "构建用户管理 REST API，支持中文和日语"

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_update_objective_max_boundary(client: TestClient):
    """Test objective at exact max length boundary."""
    session_id = f"test_session_obj_boundary_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Original")

    # Exactly 2000 chars should succeed
    response = client.patch(
        f"/api/v1/goals/{session_id}/objective",
        json={"objective": "a" * 2000},
    )
    assert response.status_code == 200

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_get_goal_status_includes_pause_reason(client: TestClient):
    """GET /goals/status should include reason when pause_reason is in metadata."""
    session_id = f"test_session_reason_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Orphaned Goal")

    # Simulate server restart: manually set PAUSED with reason
    goal.status = GoalStatus.PAUSED
    goal.metadata["pause_reason"] = "Server restarted — resume when ready"
    await provider._storage.save_goal(goal)

    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["goal"] is not None
    assert data["goal"]["status"] == "paused"
    assert data["goal"]["reason"] == "Server restarted — resume when ready"

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_get_goal_status_no_reason_when_active(client: TestClient):
    """Active goals should not have a reason field."""
    session_id = f"test_session_no_reason_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Active Goal")

    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["goal"] is not None
    assert data["goal"]["status"] == "active"
    assert "reason" not in data["goal"]

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_resume_clears_pause_reason(client: TestClient):
    """After resume, pause_reason should be cleared from metadata."""
    session_id = f"test_session_resume_clear_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.create_goal(session_id, "Resumable Goal")

    # Simulate orphan pause
    goal.status = GoalStatus.PAUSED
    goal.metadata["pause_reason"] = "Server restarted — resume when ready"
    await provider._storage.save_goal(goal)

    # Verify reason is present
    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.json()["goal"]["reason"] == "Server restarted — resume when ready"

    # Resume
    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "resume"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "active"

    # Verify reason is cleared
    response = client.get(f"/api/v1/goals/{session_id}/status")
    data = response.json()
    assert data["goal"]["status"] == "active"
    assert "reason" not in data["goal"]

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_pause_with_user_note(client: TestClient):
    """User-initiated pause should persist optional note as pause_reason."""
    session_id = f"test_session_pause_note_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "Pausable Goal")

    response = client.post(
        f"/api/v1/goals/{session_id}/status",
        json={"action": "pause", "note": "Waiting for client feedback"},
    )
    assert response.status_code == 200

    response = client.get(f"/api/v1/goals/{session_id}/status")
    data = response.json()
    assert data["goal"]["status"] == "paused"
    assert data["goal"]["reason"] == "Waiting for client feedback"

    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_wait_and_unwait(client: TestClient):
    """WAIT / unwait actions should transition goal status."""
    session_id = f"test_session_wait_{uuid.uuid4().hex}"

    provider = GoalRegistry.get_or_create_provider(session_id)
    await provider.create_goal(session_id, "CI Goal")

    response = client.post(
        f"/api/v1/goals/{session_id}/status",
        json={"action": "wait", "wait_reason": "GitHub Actions running"},
    )
    assert response.status_code == 200

    response = client.get(f"/api/v1/goals/{session_id}/status")
    data = response.json()
    assert data["goal"]["status"] == "wait"
    assert data["goal"]["wait_reason"] == "GitHub Actions running"

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "unwait"})
    assert response.status_code == 200
    assert response.json()["new_status"] == "active"

    GoalRegistry.unregister(session_id)
