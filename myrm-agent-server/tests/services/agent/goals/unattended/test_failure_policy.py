"""What becomes of a goal when its unattended start fails, and what a failure leaves alone."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus


def _goal(goal_id: str, status: GoalStatus) -> Goal:
    return Goal(goal_id=goal_id, session_id="chat-4", objective="Run", status=status, budget=GoalBudget(max_turns=5))


@pytest.mark.asyncio
async def test_failure_policy_marks_needs_human_review() -> None:
    from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-review",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()
    provider.get_goal.return_value = goal

    with patch(
        "app.services.agent.goals.unattended.trigger.trigger_goal_stream",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        ok = await trigger_goal_stream_with_failure_policy(
            "chat-1",
            goal,
            provider,
            on_failure="needs_human_review",
            context="test",
        )

    assert ok is False
    provider.update_status.assert_called_once_with("g-review", GoalStatus.NEEDS_HUMAN_REVIEW)


@pytest.mark.asyncio
async def test_failure_policy_keep_active_skips_status_update() -> None:
    from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-active",
        session_id="chat-2",
        objective="Loop",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goals.unattended.trigger.trigger_goal_stream",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        ok = await trigger_goal_stream_with_failure_policy(
            "chat-2",
            goal,
            provider,
            on_failure="keep_active",
            context="loop restart",
        )

    assert ok is False
    provider.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_failure_policy_success_returns_true() -> None:
    from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-ok",
        session_id="chat-3",
        objective="Run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goals.unattended.trigger.trigger_goal_stream",
        new_callable=AsyncMock,
    ) as mock_trigger:
        ok = await trigger_goal_stream_with_failure_policy(
            "chat-3",
            goal,
            provider,
            on_failure="needs_human_review",
        )

    assert ok is True
    mock_trigger.assert_awaited_once()
    provider.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_handle_unattended_goal_stream_failure_publishes_notification() -> None:
    from app.services.agent.goals.unattended import handle_unattended_goal_stream_failure

    provider = AsyncMock()
    provider.get_goal.return_value = _goal("g-runtime", GoalStatus.ACTIVE)
    mock_bus = MagicMock()

    with (
        patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ),
        patch(
            "app.services.agent.goals.unattended.failure.resolve_user_locale",
            new_callable=AsyncMock,
            return_value="en",
        ),
        patch(
            "app.channels.i18n.engine.channel_t",
            side_effect=lambda _locale, key: key,
        ),
    ):
        await handle_unattended_goal_stream_failure(
            "chat-4",
            "g-runtime",
            provider,
            on_failure="needs_human_review",
            context="runtime test",
        )

    provider.update_status.assert_called_once_with("g-runtime", GoalStatus.NEEDS_HUMAN_REVIEW)
    mock_bus.publish.assert_called_once()
    published = mock_bus.publish.call_args[0][0]
    assert published.data["meta_data"]["kind"] == "goal_needs_review"
    assert published.data["meta_data"]["chat_id"] == "chat-4"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GoalStatus.WAIT, GoalStatus.PAUSED, GoalStatus.COMPLETE])
async def test_failure_after_the_run_moved_the_goal_on_keeps_that_state(status: GoalStatus) -> None:
    from app.services.agent.goals.unattended import handle_unattended_goal_stream_failure

    provider = AsyncMock()
    provider.get_goal.return_value = _goal("g-moved", status)

    with patch(
        "app.services.agent.goals.unattended.failure.publish_goal_needs_review_notification",
        new_callable=AsyncMock,
    ) as publish:
        await handle_unattended_goal_stream_failure(
            "chat-4",
            "g-moved",
            provider,
            on_failure="needs_human_review",
            context="runtime test",
        )

    provider.update_status.assert_not_called()
    publish.assert_not_awaited()
