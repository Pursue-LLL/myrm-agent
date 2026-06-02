from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goal_registry import GoalRegistry


@pytest.fixture
def client():
    from fastapi import FastAPI
    from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

    from app.api.goals.router import router as goals_router

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")

    mock_features = MagicMock()
    mock_features.enabled.return_value = True

    with (
        patch("app.api.goals.router.get_features", return_value=mock_features),
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend("/tmp/test_storage")),
    ):
        with TestClient(app) as client:
            yield client

@pytest.mark.asyncio
async def test_update_goal_budget(client: TestClient):
    """Test updating the budget of a goal."""
    session_id = "test_session_budget"
    
    provider = GoalRegistry.get_or_create_provider(session_id)
    
    # Check if goal already exists from previous test run
    goal = await provider.get_active_goal(session_id)
    if not goal:
        goal = await provider.create_goal(session_id, "Test Budget Goal")
    
    # 1. Update budget for active goal
    # Since we are reusing the goal from previous runs, we just check the increment
    initial_tokens = goal.budget.max_tokens if goal.budget and goal.budget.max_tokens else 0
    
    response = client.post(
        f"/api/v1/goals/{session_id}/budget",
        json={"additional_tokens": 5000}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["new_budget"]["max_tokens"] == initial_tokens + 5000
    
    # 2. Update budget again
    response = client.post(
        f"/api/v1/goals/{session_id}/budget",
        json={"additional_tokens": 2000}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_budget"]["max_tokens"] == initial_tokens + 7000
    
    # 3. Test invalid tokens
    response = client.post(
        f"/api/v1/goals/{session_id}/budget",
        json={"additional_tokens": -100}
    )
    assert response.status_code == 400
    
    GoalRegistry.unregister(session_id)
