import uuid

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.goals.goal_registry import GoalRegistry


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
    provider = GoalRegistry.register(session_id)
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
    provider = GoalRegistry.register(session_id)
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


@pytest.mark.asyncio
async def test_update_status_invalid_action(client: TestClient):
    """Test updating status with invalid action."""
    session_id = f"test_session_invalid_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)

    # Check if goal already exists from previous test run
    goal = await provider.get_active_goal(session_id)
    if not goal:
        goal = await provider.create_goal(session_id, "Test API Goal")

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "invalid_action"})
    assert response.status_code == 400
    assert "Invalid action" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_status_no_active_goal(client: TestClient):
    """Test updating status when no active goal exists."""
    session_id = f"test_session_no_active_{uuid.uuid4().hex}"

    # Create provider but no goal
    GoalRegistry.register(session_id)

    response = client.post(f"/api/v1/goals/{session_id}/status", json={"action": "pause"})
    assert response.status_code == 404
    assert "No active goal found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_subgoal_api(client: TestClient):
    """Test the subgoal management API endpoints."""
    session_id = f"test_session_subgoals_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
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


@pytest.mark.asyncio
async def test_goal_queue_api(client: TestClient):
    """Test the queue management API: list, cancel, reorder."""
    session_id = f"test_session_queue_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)

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


@pytest.mark.asyncio
async def test_get_goal_status_includes_pause_reason(client: TestClient):
    """GET /goals/status should include reason when pause_reason is in metadata."""
    session_id = f"test_session_reason_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
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


@pytest.mark.asyncio
async def test_get_goal_status_no_reason_when_active(client: TestClient):
    """Active goals should not have a reason field."""
    session_id = f"test_session_no_reason_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
    await provider.create_goal(session_id, "Active Goal")

    response = client.get(f"/api/v1/goals/{session_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["goal"] is not None
    assert data["goal"]["status"] == "active"
    assert "reason" not in data["goal"]


@pytest.mark.asyncio
async def test_resume_clears_pause_reason(client: TestClient):
    """After resume, pause_reason should be cleared from metadata."""
    session_id = f"test_session_resume_clear_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
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


@pytest.mark.asyncio
async def test_pause_with_user_note(client: TestClient):
    """User-initiated pause should persist optional note as pause_reason."""
    session_id = f"test_session_pause_note_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
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


@pytest.mark.asyncio
async def test_wait_and_unwait(client: TestClient):
    """WAIT / unwait actions should transition goal status."""
    session_id = f"test_session_wait_{uuid.uuid4().hex}"

    provider = GoalRegistry.register(session_id)
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
