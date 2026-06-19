"""Orchestrator goal passthrough tests.

Verifies that all GoalBudgetRequest fields (especially max_turns and
protected_paths) are correctly forwarded from the request model to the
harness GoalBudget and GoalProvider.create_goal calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.params.models import GoalBudgetRequest


@pytest.fixture
def goal_budget_full():
    return GoalBudgetRequest(
        max_tokens=50000,
        max_usd=5.0,
        max_time_seconds=3600,
        max_turns=30,
        convergence_window=3,
        loop_on_pause=True,
        max_loop_restarts=5,
        acceptance_criteria=[{"type": "shell", "command": "pytest"}],
        constraints=["No destructive operations"],
        protected_paths=["*.env", "config/**"],
        ui_summary="Full budget test",
    )


class TestGoalBudgetToHarnessBudget:
    def test_max_turns_forwarded_to_goal_budget(self, goal_budget_full: GoalBudgetRequest):
        from myrm_agent_harness.agent.goals.types import GoalBudget

        budget = GoalBudget(
            max_tokens=goal_budget_full.max_tokens,
            max_usd=goal_budget_full.max_usd,
            max_time_seconds=goal_budget_full.max_time_seconds,
            max_turns=goal_budget_full.max_turns,
            convergence_window=goal_budget_full.convergence_window,
            loop_on_pause=goal_budget_full.loop_on_pause,
            max_loop_restarts=goal_budget_full.max_loop_restarts,
        )
        assert budget.max_turns == 30
        assert budget.max_tokens == 50000
        assert budget.max_usd == 5.0
        assert budget.max_time_seconds == 3600
        assert budget.convergence_window == 3
        assert budget.loop_on_pause is True
        assert budget.max_loop_restarts == 5

    def test_none_fields_produce_none_budget(self):
        from myrm_agent_harness.agent.goals.types import GoalBudget

        req = GoalBudgetRequest()
        budget = GoalBudget(
            max_tokens=req.max_tokens,
            max_usd=req.max_usd,
            max_time_seconds=req.max_time_seconds,
            max_turns=req.max_turns,
            convergence_window=req.convergence_window,
            loop_on_pause=req.loop_on_pause,
            max_loop_restarts=req.max_loop_restarts,
        )
        assert budget.max_tokens is None
        assert budget.max_usd is None
        assert budget.max_time_seconds is None
        assert budget.max_turns is None
        assert budget.convergence_window is None
        assert budget.loop_on_pause is False
        assert budget.max_loop_restarts == 10


class TestGoalCreationPassthrough:
    @pytest.mark.asyncio
    async def test_create_goal_receives_protected_paths(self, goal_budget_full: GoalBudgetRequest):
        mock_provider = AsyncMock()
        mock_provider.get_active_goal = AsyncMock(return_value=None)
        mock_provider.create_goal = AsyncMock()

        from myrm_agent_harness.agent.goals.types import GoalBudget

        budget = GoalBudget(
            max_tokens=goal_budget_full.max_tokens,
            max_usd=goal_budget_full.max_usd,
            max_time_seconds=goal_budget_full.max_time_seconds,
            max_turns=goal_budget_full.max_turns,
            convergence_window=goal_budget_full.convergence_window,
            loop_on_pause=goal_budget_full.loop_on_pause,
            max_loop_restarts=goal_budget_full.max_loop_restarts,
        )

        await mock_provider.create_goal(
            session_id="test-session",
            objective="User requested goal",
            budget=budget,
            acceptance_criteria=goal_budget_full.acceptance_criteria,
            constraints=goal_budget_full.constraints,
            protected_paths=goal_budget_full.protected_paths,
            ui_summary=goal_budget_full.ui_summary,
        )

        mock_provider.create_goal.assert_called_once()
        call_kwargs = mock_provider.create_goal.call_args[1]
        assert call_kwargs["protected_paths"] == ["*.env", "config/**"]
        assert call_kwargs["constraints"] == ["No destructive operations"]
        assert call_kwargs["budget"].max_turns == 30
        assert call_kwargs["budget"].max_tokens == 50000
        assert call_kwargs["ui_summary"] == "Full budget test"

    @pytest.mark.asyncio
    async def test_existing_goal_updates_budget_only(self, goal_budget_full: GoalBudgetRequest):
        from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus

        existing_goal = Goal(
            goal_id="existing-1",
            session_id="test-session",
            objective="Old goal",
            status=GoalStatus.ACTIVE,
        )

        mock_provider = AsyncMock()
        mock_provider.get_active_goal = AsyncMock(return_value=existing_goal)
        mock_provider.set_budget = AsyncMock()

        budget = GoalBudget(
            max_tokens=goal_budget_full.max_tokens,
            max_usd=goal_budget_full.max_usd,
            max_time_seconds=goal_budget_full.max_time_seconds,
            max_turns=goal_budget_full.max_turns,
            convergence_window=goal_budget_full.convergence_window,
            loop_on_pause=goal_budget_full.loop_on_pause,
            max_loop_restarts=goal_budget_full.max_loop_restarts,
        )

        await mock_provider.set_budget(existing_goal.goal_id, budget)

        mock_provider.set_budget.assert_called_once_with("existing-1", budget)
        assert budget.max_turns == 30

    @pytest.mark.asyncio
    async def test_none_protected_paths_not_passed(self):
        req = GoalBudgetRequest(max_tokens=10000)
        mock_provider = AsyncMock()
        mock_provider.get_active_goal = AsyncMock(return_value=None)
        mock_provider.create_goal = AsyncMock()

        from myrm_agent_harness.agent.goals.types import GoalBudget

        budget = GoalBudget(
            max_tokens=req.max_tokens,
            max_usd=req.max_usd,
            max_time_seconds=req.max_time_seconds,
            max_turns=req.max_turns,
        )

        await mock_provider.create_goal(
            session_id="s1",
            objective="User requested goal",
            budget=budget,
            acceptance_criteria=req.acceptance_criteria,
            constraints=req.constraints,
            protected_paths=req.protected_paths,
            ui_summary=req.ui_summary,
        )

        call_kwargs = mock_provider.create_goal.call_args[1]
        assert call_kwargs["protected_paths"] is None
        assert call_kwargs["constraints"] is None
        assert call_kwargs["budget"].max_turns is None
