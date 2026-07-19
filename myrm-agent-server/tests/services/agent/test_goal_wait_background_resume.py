"""Tests for goal WAIT resume after background bash job finish."""

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_PID_KEY
from myrm_agent_harness.api.hooks import BackgroundJobFinishResult


@pytest.mark.asyncio
async def test_maybe_resume_goal_after_background_job_exits_wait_and_triggers_stream():
    from app.services.agent.goal_wait_background_resume import maybe_resume_goal_after_background_job

    wait_goal = Goal(
        goal_id="g1",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.WAIT,
        metadata={WAIT_ON_BACKGROUND_PID_KEY: 4242},
        budget=GoalBudget(max_turns=5),
    )
    active_goal = Goal(
        goal_id="g1",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()
    provider.get_latest_goal.return_value = wait_goal
    provider.exit_wait.return_value = active_goal
    provider.get_goal.return_value = active_goal

    result = BackgroundJobFinishResult(
        session_id="chat-1",
        pid=4242,
        command="npm run build",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    with (
        patch(
            "app.services.agent.goal_registry.GoalRegistry.get_provider",
            return_value=provider,
        ),
        patch(
            "app.services.agent.goal_stream_trigger.trigger_goal_stream",
            new_callable=AsyncMock,
        ) as mock_trigger,
    ):
        resumed = await maybe_resume_goal_after_background_job(result)

    assert resumed is True
    provider.exit_wait.assert_called_once_with("g1")
    mock_trigger.assert_awaited_once_with("chat-1", active_goal)


@pytest.mark.asyncio
async def test_maybe_resume_goal_skips_unmatched_pid():
    from app.services.agent.goal_wait_background_resume import maybe_resume_goal_after_background_job

    goal = Goal(
        goal_id="g1",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.WAIT,
        metadata={WAIT_ON_BACKGROUND_PID_KEY: 1111},
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()
    provider.get_latest_goal.return_value = goal

    result = BackgroundJobFinishResult(
        session_id="chat-1",
        pid=9999,
        command="npm run build",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    with (
        patch(
            "app.services.agent.goal_registry.GoalRegistry.get_provider",
            return_value=provider,
        ),
        patch(
            "app.services.agent.goal_stream_trigger.trigger_goal_stream",
            new_callable=AsyncMock,
        ) as mock_trigger,
    ):
        resumed = await maybe_resume_goal_after_background_job(result)

    assert resumed is False
    provider.exit_wait.assert_not_called()
    mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_resume_goal_returns_false_when_stream_trigger_fails():
    from app.services.agent.goal_wait_background_resume import maybe_resume_goal_after_background_job

    wait_goal = Goal(
        goal_id="g1",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.WAIT,
        metadata={WAIT_ON_BACKGROUND_PID_KEY: 4242},
        budget=GoalBudget(max_turns=5),
    )
    active_goal = Goal(
        goal_id="g1",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()
    provider.get_latest_goal.return_value = wait_goal
    provider.exit_wait.return_value = active_goal
    provider.get_goal.return_value = active_goal

    result = BackgroundJobFinishResult(
        session_id="chat-1",
        pid=4242,
        command="npm run build",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    with (
        patch(
            "app.services.agent.goal_registry.GoalRegistry.get_provider",
            return_value=provider,
        ),
        patch(
            "app.services.agent.goal_stream_trigger.trigger_goal_stream",
            new_callable=AsyncMock,
            side_effect=RuntimeError("stream failed"),
        ),
    ):
        resumed = await maybe_resume_goal_after_background_job(result)

    assert resumed is False
    provider.exit_wait.assert_called_once_with("g1")
