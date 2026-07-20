"""Tests for WAIT goal release when background jobs are orphaned on restart."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_JOB_ID_KEY
from myrm_agent_harness.agent.meta_tools.bash._background_job_store_core import BackgroundJobRecord

_JOB_ID = "c" * 32


def _goal(*, session_id: str, status: GoalStatus, wait_job_id: str | None = None) -> Goal:
    metadata: dict[str, object] = {}
    if wait_job_id is not None:
        metadata[WAIT_ON_BACKGROUND_JOB_ID_KEY] = wait_job_id
    return Goal(
        goal_id=f"goal-{session_id}",
        session_id=session_id,
        objective="Run tests",
        status=status,
        metadata=metadata,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_find_goals_to_release_matches_session_and_job_id() -> None:
    from app.services.agent.goal_wait_orphan_recovery import find_goals_to_release_from_orphaned_jobs

    orphaned = (
        BackgroundJobRecord(
            job_id=_JOB_ID,
            pid=4242,
            session_id="s1",
            command="pytest",
            status="orphaned",
            started_at=1.0,
            completed_at=None,
            exit_code=None,
            error_category=None,
            finish_processed=False,
            vault_log_ref=None,
        ),
    )
    goals = {
        "s1": _goal(session_id="s1", status=GoalStatus.WAIT, wait_job_id=_JOB_ID),
        "s2": _goal(session_id="s2", status=GoalStatus.WAIT, wait_job_id="d" * 32),
    }

    released = find_goals_to_release_from_orphaned_jobs(
        session_ids=("s1", "s2"),
        goals_by_session=goals,
        orphaned_jobs=orphaned,
    )
    assert released == ("goal-s1",)


@pytest.mark.asyncio
async def test_release_orphaned_wait_goals_updates_status() -> None:
    wait_goal = _goal(session_id="s1", status=GoalStatus.WAIT, wait_job_id=_JOB_ID)
    orphaned = BackgroundJobRecord(
        job_id=_JOB_ID,
        pid=4242,
        session_id="s1",
        command="pytest",
        status="orphaned",
        started_at=1.0,
        completed_at=None,
        exit_code=None,
        error_category=None,
        finish_processed=False,
        vault_log_ref=None,
    )

    mock_store = MagicMock()
    mock_store.list_recent.return_value = [orphaned]

    mock_storage = MagicMock()
    mock_storage.list_latest_goal_sessions = AsyncMock(return_value=["s1"])
    mock_storage.get_latest_goal_id = AsyncMock(return_value="goal-s1")
    mock_storage.get_goal = AsyncMock(return_value=wait_goal)
    mock_storage.save_goal = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.bash._background_job_store.get_background_job_store",
            return_value=mock_store,
        ),
        patch(
            "myrm_agent_harness.toolkits.storage.factory.get_storage_provider",
            return_value=MagicMock(),
        ),
        patch(
            "myrm_agent_harness.agent.goals.storage.GoalStorage",
            return_value=mock_storage,
        ),
        patch(
            "app.services.agent.goal_stream_trigger.publish_goal_needs_review_notification",
            new_callable=AsyncMock,
        ) as notify,
    ):
        from app.services.agent.goal_wait_orphan_recovery import release_orphaned_wait_goals

        await release_orphaned_wait_goals()

    assert wait_goal.status == GoalStatus.NEEDS_HUMAN_REVIEW
    assert WAIT_ON_BACKGROUND_JOB_ID_KEY not in wait_goal.metadata
    mock_storage.save_goal.assert_awaited_once()
    notify.assert_awaited_once_with("s1", "goal-s1")
