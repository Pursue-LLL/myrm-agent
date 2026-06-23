"""Tests for pause_orphaned_active_goals lifecycle function."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.goals.types import Goal, GoalStatus


@pytest.mark.asyncio
async def test_pause_orphaned_active_goals_no_active() -> None:
    """Should do nothing when no active sessions exist."""
    mock_storage = MagicMock()
    mock_storage.list_active_sessions = AsyncMock(return_value=[])

    with (
        patch(
            "myrm_agent_harness.toolkits.storage.factory.get_storage_provider",
            return_value=MagicMock(),
        ),
        patch(
            "myrm_agent_harness.agent.goals.storage.GoalStorage",
            return_value=mock_storage,
        ),
    ):
        from app.lifecycle.system import pause_orphaned_active_goals

        await pause_orphaned_active_goals()

    mock_storage.list_active_sessions.assert_awaited_once()


@pytest.mark.asyncio
async def test_pause_orphaned_active_goals_pauses_active() -> None:
    """Should transition ACTIVE goals to PAUSED with reason."""
    goal = Goal(
        goal_id="g1",
        session_id="s1",
        objective="Test",
        status=GoalStatus.ACTIVE,
    )

    mock_storage = MagicMock()
    mock_storage.list_active_sessions = AsyncMock(return_value=["s1"])
    mock_storage.get_active_goal_id = AsyncMock(return_value="g1")
    mock_storage.get_goal = AsyncMock(return_value=goal)
    mock_storage.save_goal = AsyncMock()

    mock_notification = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.storage.factory.get_storage_provider",
            return_value=MagicMock(),
        ),
        patch(
            "myrm_agent_harness.agent.goals.storage.GoalStorage",
            return_value=mock_storage,
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notification,
        ),
    ):
        from app.lifecycle.system import pause_orphaned_active_goals

        await pause_orphaned_active_goals()

    assert goal.status == GoalStatus.PAUSED
    assert goal.metadata["pause_reason"] == "Server restarted — resume when ready"
    mock_storage.save_goal.assert_awaited_once_with(goal)
    mock_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_pause_orphaned_active_goals_skips_non_active() -> None:
    """Should skip goals already transitioned away from ACTIVE."""
    goal = Goal(
        goal_id="g2",
        session_id="s2",
        objective="Already paused",
        status=GoalStatus.PAUSED,
    )

    mock_storage = MagicMock()
    mock_storage.list_active_sessions = AsyncMock(return_value=["s2"])
    mock_storage.get_active_goal_id = AsyncMock(return_value="g2")
    mock_storage.get_goal = AsyncMock(return_value=goal)
    mock_storage.save_goal = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.storage.factory.get_storage_provider",
            return_value=MagicMock(),
        ),
        patch(
            "myrm_agent_harness.agent.goals.storage.GoalStorage",
            return_value=mock_storage,
        ),
    ):
        from app.lifecycle.system import pause_orphaned_active_goals

        await pause_orphaned_active_goals()

    mock_storage.save_goal.assert_not_awaited()
    assert goal.status == GoalStatus.PAUSED


@pytest.mark.asyncio
async def test_pause_orphaned_active_goals_handles_exception() -> None:
    """Should not crash on storage errors."""
    with (
        patch(
            "myrm_agent_harness.toolkits.storage.factory.get_storage_provider",
            side_effect=RuntimeError("storage init failed"),
        ),
    ):
        from app.lifecycle.system import pause_orphaned_active_goals

        # Should not raise
        await pause_orphaned_active_goals()
