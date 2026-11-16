"""Between turns a session has no registered provider, yet its goals are in storage: the goals routers still serve them.

One route per goals module (router, queue, constraints), so a module that stops resolving through the registry fails here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.mark.asyncio
async def test_each_goals_module_serves_a_session_between_turns_from_storage(client: TestClient) -> None:
    session_id = "between-turns"
    goal = await GoalRegistry.get_or_create_provider(session_id).create_goal(
        session_id=session_id, objective="ship the weekly report"
    )
    GoalRegistry.unregister(session_id)

    status = client.get(f"/api/v1/goals/{session_id}/status")
    queue = client.get(f"/api/v1/goals/{session_id}/queue")
    constraints = client.get(f"/api/v1/goals/{session_id}/constraints")

    assert [r.status_code for r in (status, queue, constraints)] == [200, 200, 200]
    assert status.json()["goal"]["goal_id"] == goal.goal_id
    assert queue.json() == {"queue": []}
    assert constraints.json() == {"constraints": []}
    assert GoalRegistry.get_provider(session_id) is None
