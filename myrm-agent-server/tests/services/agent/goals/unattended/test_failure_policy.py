"""What becomes of a goal when its unattended start fails, and what a failure leaves alone.

The goal lives in real storage and the policy reads and changes it through the registry, as it does in production: a
failure is handled once the turn has ended and released its provider, so the session has none registered then.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.ai_agents.general_agent.goal_learnings import build_loop_restart_callback
from app.services.agent.goals.goal_registry import GoalRegistry

_TRIGGER_STREAM = "app.services.agent.goals.unattended.trigger.trigger_goal_stream"
_NOTIFY = "app.services.agent.goals.unattended.failure.publish_goal_needs_review_notification"


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> Iterator[str]:
    session_id = f"failure-policy-{request.node.name}"
    yield session_id
    GoalRegistry.unregister(session_id)


async def _goal_in(chat_id: str, status: GoalStatus = GoalStatus.ACTIVE) -> str:
    """Create the chat's goal and move it to ``status``; returns its id."""
    provider = GoalRegistry.resolve_provider(chat_id)
    goal = await provider.create_goal(chat_id, "Run")
    if status is not GoalStatus.ACTIVE:
        await provider.update_status(goal.goal_id, status)
    return goal.goal_id


async def _status_of(chat_id: str, goal_id: str) -> GoalStatus:
    goal = await GoalRegistry.resolve_provider(chat_id).get_goal(goal_id)
    assert goal is not None
    return goal.status


@pytest.mark.asyncio
async def test_failure_policy_marks_needs_human_review(chat_id: str) -> None:
    from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

    goal_id = await _goal_in(chat_id)
    goal = await GoalRegistry.resolve_provider(chat_id).get_goal(goal_id)
    assert goal is not None

    with patch(_TRIGGER_STREAM, new_callable=AsyncMock, side_effect=RuntimeError("boom")), patch(_NOTIFY, new_callable=AsyncMock):
        ok = await trigger_goal_stream_with_failure_policy(chat_id, goal, context="test")

    assert ok is False
    assert await _status_of(chat_id, goal_id) is GoalStatus.NEEDS_HUMAN_REVIEW
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_a_loop_restart_that_cannot_start_leaves_the_goal_for_review(chat_id: str) -> None:
    """A loop restart is a start like any other: when it fails nothing else runs the goal, so it waits for its owner."""
    goal_id = await _goal_in(chat_id)
    goal = await GoalRegistry.resolve_provider(chat_id).get_goal(goal_id)
    assert goal is not None

    with patch(_TRIGGER_STREAM, new_callable=AsyncMock, side_effect=RuntimeError("boom")), patch(_NOTIFY, new_callable=AsyncMock):
        await build_loop_restart_callback()(chat_id, goal)

    assert await _status_of(chat_id, goal_id) is GoalStatus.NEEDS_HUMAN_REVIEW


@pytest.mark.asyncio
async def test_failure_policy_success_returns_true(chat_id: str) -> None:
    from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

    goal_id = await _goal_in(chat_id)
    goal = await GoalRegistry.resolve_provider(chat_id).get_goal(goal_id)
    assert goal is not None

    with patch(_TRIGGER_STREAM, new_callable=AsyncMock) as mock_trigger:
        ok = await trigger_goal_stream_with_failure_policy(chat_id, goal)

    assert ok is True
    mock_trigger.assert_awaited_once_with(chat_id, goal, context="goal stream")
    assert await _status_of(chat_id, goal_id) is GoalStatus.ACTIVE


@pytest.mark.asyncio
async def test_handle_unattended_goal_stream_failure_publishes_notification(chat_id: str) -> None:
    from app.services.agent.goals.unattended import handle_unattended_goal_stream_failure

    goal_id = await _goal_in(chat_id)
    mock_bus = MagicMock()

    with (
        patch("app.services.event.app_event_bus.get_event_bus", return_value=mock_bus),
        patch("app.services.agent.goals.unattended.failure.resolve_user_locale", new_callable=AsyncMock, return_value="en"),
        patch("app.channels.i18n.engine.channel_t", side_effect=lambda _locale, key: key),
    ):
        await handle_unattended_goal_stream_failure(chat_id, goal_id, context="runtime test")

    assert await _status_of(chat_id, goal_id) is GoalStatus.NEEDS_HUMAN_REVIEW
    mock_bus.publish.assert_called_once()
    published = mock_bus.publish.call_args[0][0]
    assert published.data["meta_data"]["kind"] == "goal_needs_review"
    assert published.data["meta_data"]["chat_id"] == chat_id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GoalStatus.WAIT, GoalStatus.PAUSED, GoalStatus.COMPLETE])
async def test_failure_after_the_run_moved_the_goal_on_keeps_that_state(chat_id: str, status: GoalStatus) -> None:
    from app.services.agent.goals.unattended import handle_unattended_goal_stream_failure

    goal_id = await _goal_in(chat_id, status)

    with patch(_NOTIFY, new_callable=AsyncMock) as publish:
        await handle_unattended_goal_stream_failure(chat_id, goal_id, context="runtime test")

    assert await _status_of(chat_id, goal_id) is status
    publish.assert_not_awaited()
