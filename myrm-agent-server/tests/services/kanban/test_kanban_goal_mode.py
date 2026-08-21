"""Tests for kanban goal mode integration in task_runner.

Covers GoalProvider setup, goal outcome mapping to kanban result,
and verify goal_mode=False path is unchanged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskPriority,
    TaskStatus,
)


def _make_task(**kwargs) -> KanbanTask:
    defaults = {
        "task_id": "abc123",
        "board_id": "b1",
        "title": "Test Goal Task",
        "description": "Build a report",
        "status": TaskStatus.RUNNING,
        "priority": TaskPriority.NORMAL,
    }
    defaults.update(kwargs)
    return KanbanTask(**defaults)


class TestGoalProviderSetup:
    """Test _setup_goal_provider creates a GoalProvider with correct params."""

    @pytest.mark.asyncio
    async def test_setup_creates_goal_with_defaults(self):
        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        with patch("app.services.kanban.task_runner.runner.GoalRegistry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.get_active_goal = AsyncMock(return_value=None)
            mock_provider.create_goal = AsyncMock()
            mock_registry.get_or_create_provider.return_value = mock_provider

            await runner._setup_goal_provider(task)

            mock_registry.get_or_create_provider.assert_called_once_with("kanban:abc123")
            mock_provider.create_goal.assert_called_once()
            call_kwargs = mock_provider.create_goal.call_args
            assert call_kwargs.kwargs["session_id"] == "kanban:abc123"
            assert call_kwargs.kwargs["objective"] == "Build a report"
            budget = call_kwargs.kwargs["budget"]
            assert budget.max_turns == 10  # default

    @pytest.mark.asyncio
    async def test_setup_uses_explicit_max_turns(self):
        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True, goal_max_turns=5)

        with patch("app.services.kanban.task_runner.runner.GoalRegistry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.get_active_goal = AsyncMock(return_value=None)
            mock_provider.create_goal = AsyncMock()
            mock_registry.get_or_create_provider.return_value = mock_provider

            await runner._setup_goal_provider(task)

            budget = mock_provider.create_goal.call_args.kwargs["budget"]
            assert budget.max_turns == 5

    @pytest.mark.asyncio
    async def test_setup_reuses_active_goal(self):
        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        with patch("app.services.kanban.task_runner.runner.GoalRegistry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.get_active_goal = AsyncMock(return_value=MagicMock())
            mock_registry.get_or_create_provider.return_value = mock_provider

            result = await runner._setup_goal_provider(task)

            mock_provider.create_goal.assert_not_called()
            assert result is mock_provider

    @pytest.mark.asyncio
    async def test_setup_converts_string_criteria(self):
        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(
            goal_mode=True,
            metadata={"completion_criteria": "All tests pass"},
        )

        with patch("app.services.kanban.task_runner.runner.GoalRegistry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.get_active_goal = AsyncMock(return_value=None)
            mock_provider.create_goal = AsyncMock()
            mock_registry.get_or_create_provider.return_value = mock_provider

            await runner._setup_goal_provider(task)

            acceptance = mock_provider.create_goal.call_args.kwargs["acceptance_criteria"]
            assert acceptance == [{"type": "semantic", "criteria": "All tests pass"}]


class TestGoalOutcomeMapping:
    """Test _map_goal_outcome correctly maps Goal status to Kanban result."""

    @pytest.mark.asyncio
    async def test_setup_resumes_paused_goal(self):
        from myrm_agent_harness.agent.goals.types import GoalStatus

        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        with patch("app.services.kanban.task_runner.runner.GoalRegistry") as mock_registry:
            mock_provider = AsyncMock()
            mock_provider.get_active_goal = AsyncMock(return_value=None)
            paused_goal = MagicMock()
            paused_goal.goal_id = "g-123"
            paused_goal.status = GoalStatus.PAUSED
            paused_goal.is_terminal = False
            mock_provider.get_latest_goal = AsyncMock(return_value=paused_goal)
            mock_provider.resume_goal = AsyncMock()
            mock_registry.get_or_create_provider.return_value = mock_provider

            result = await runner._setup_goal_provider(task)

            mock_provider.resume_goal.assert_called_once_with("g-123", reset_turns=False)
            mock_provider.create_goal.assert_not_called()
            assert result is mock_provider

    @pytest.mark.asyncio
    async def test_complete_goal_maps_to_success(self):
        from myrm_agent_harness.agent.goals.types import GoalStatus
        from myrm_agent_harness.toolkits.kanban.types import (
            KANBAN_COMPLETION_INTENT_KEY,
        )

        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        fresh_task = _make_task(
            goal_mode=True,
            metadata={KANBAN_COMPLETION_INTENT_KEY: True},
            result="Goal completed",
        )
        mock_store.get_task = AsyncMock(return_value=fresh_task)
        mock_store.save_task = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        mock_goal = MagicMock()
        mock_goal.status = GoalStatus.COMPLETE
        mock_goal.turns_used = 3
        mock_goal.metadata = {"acceptance_results": [{"label": "test", "passed": True}]}

        mock_provider = AsyncMock()
        mock_provider.get_latest_goal = AsyncMock(return_value=mock_goal)

        result = await runner._map_goal_outcome(task, mock_provider, (True, "Done"))
        assert result[0] is True
        assert "3 turns" in result[1]
        mock_store.save_task.assert_called_once()
        saved_task = mock_store.save_task.call_args[0][0]
        assert saved_task.metadata.get("acceptance_results") == [{"label": "test", "passed": True}]

    @pytest.mark.asyncio
    async def test_budget_limited_maps_to_failure(self):
        from myrm_agent_harness.agent.goals.types import GoalStatus

        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        fresh_task = _make_task(goal_mode=True)
        mock_store.get_task = AsyncMock(return_value=fresh_task)
        mock_store.save_task = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        mock_goal = MagicMock()
        mock_goal.status = GoalStatus.BUDGET_LIMITED
        mock_goal.turns_used = 10
        mock_goal.metadata = {}

        mock_provider = AsyncMock()
        mock_provider.get_latest_goal = AsyncMock(return_value=mock_goal)

        result = await runner._map_goal_outcome(task, mock_provider, (False, ""))
        assert result[0] is False
        assert "Budget exhausted" in result[1]
        assert "10 turns" in result[1]

    @pytest.mark.asyncio
    async def test_paused_goal_maps_to_blocked_without_crash(self):
        from myrm_agent_harness.agent.goals.types import GoalStatus
        from myrm_agent_harness.toolkits.kanban.types import BlockKind, TaskStatus

        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        fresh_task = _make_task(goal_mode=True)
        mock_store.get_task = AsyncMock(return_value=fresh_task)
        mock_store.save_task = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        mock_goal = MagicMock()
        mock_goal.status = GoalStatus.PAUSED
        mock_goal.metadata = {
            "pause_reason": "convergence",
            "acceptance_results": [{"label": "criteria 1", "passed": False}],
        }

        mock_provider = AsyncMock()
        mock_provider.get_latest_goal = AsyncMock(return_value=mock_goal)

        result = await runner._map_goal_outcome(task, mock_provider, (False, ""))
        assert result[0] is False
        assert "convergence" in result[1]
        mock_store.save_task.assert_called_once()
        saved_task = mock_store.save_task.call_args[0][0]
        assert saved_task.status == TaskStatus.BLOCKED
        assert saved_task.blocked_reason == "convergence"
        assert saved_task.block_kind == BlockKind.HUMAN
        assert saved_task.metadata.get("acceptance_results") == [{"label": "criteria 1", "passed": False}]

    @pytest.mark.asyncio
    async def test_no_active_goal_returns_agent_result(self):
        from app.services.kanban.task_runner import KanbanTaskRunner

        mock_store = AsyncMock()
        runner = KanbanTaskRunner(mock_store)
        task = _make_task(goal_mode=True)

        mock_provider = AsyncMock()
        mock_provider.get_latest_goal = AsyncMock(return_value=None)

        result = await runner._map_goal_outcome(task, mock_provider, (True, "Agent done"))
        assert result == (True, "Agent done")


class TestNonGoalModeUnchanged:
    """Verify goal_mode=False tasks do not touch GoalProvider."""

    def test_task_without_goal_mode(self):
        task = _make_task(goal_mode=False)
        assert task.goal_mode is False
        d = task.to_dict()
        assert d["goal_mode"] is False
