"""Tests for Goal session setup (protected paths and tamper snapshot, no planner sub-agent)."""

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.goals.goal_interceptor import apply_goal_session_invariants
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus


def _make_goal(goal_id: str = "g1", session_id: str = "s1") -> Goal:
    return Goal(
        goal_id=goal_id,
        session_id=session_id,
        objective="Write a scraper",
        status=GoalStatus.ACTIVE,
    )


@pytest.fixture
def goal_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.get_active_goal.return_value = _make_goal()
    return provider


@pytest.mark.asyncio
async def test_no_active_goal_returns_early(goal_provider):
    goal_provider.get_active_goal.return_value = None

    await apply_goal_session_invariants(goal_provider, "s1")

    goal_provider.update_status.assert_not_called()


@pytest.mark.asyncio
@patch("myrm_agent_harness.agent.middlewares._session_context.set_protected_paths")
@patch("myrm_agent_harness.agent.goals.invariant_snapshot.capture_protected_snapshot")
@patch("myrm_agent_harness.agent.middlewares._session_context.get_workspace_root", return_value=".")
async def test_applies_goal_invariants_without_plan_generation(
    _mock_ws,
    mock_capture,
    mock_set_paths,
    goal_provider,
):
    goal = _make_goal()
    goal.protected_paths = ["src/main.py"]
    goal_provider.get_active_goal.return_value = goal

    await apply_goal_session_invariants(goal_provider, "s1")

    mock_set_paths.assert_called_once_with(("src/main.py",))
    mock_capture.assert_called_once()
    goal_provider.update_status.assert_not_called()
