"""Tests for WAIT goal release when background jobs are orphaned on restart.

The job ledger holds the session key of the run that started each job (`chat_<chat id>`) while goals are stored under the
chat id, so every record here carries the production key shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_JOB_ID_KEY
from myrm_agent_harness.agent.meta_tools.bash._background.job_store_core import BackgroundJobRecord

from app.services.agent.params.workspace_resolve import chat_session_id

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


def _orphaned_job(chat_id: str, job_id: str = _JOB_ID) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=job_id,
        pid=4242,
        session_id=chat_session_id(chat_id),
        command="pytest",
        status="orphaned",
        started_at=1.0,
        completed_at=None,
        exit_code=None,
        error_category=None,
        finish_processed=False,
        vault_log_ref=None,
    )


def test_find_goals_to_release_matches_chat_and_job_id() -> None:
    from app.services.agent.goals.goal_wait_orphan_recovery import find_goals_to_release_from_orphaned_jobs

    goals = {
        "s1": _goal(session_id="s1", status=GoalStatus.WAIT, wait_job_id=_JOB_ID),
        "s2": _goal(session_id="s2", status=GoalStatus.WAIT, wait_job_id="d" * 32),
        # Waits on the same job id, but the orphaned job belongs to another chat.
        "s3": _goal(session_id="s3", status=GoalStatus.WAIT, wait_job_id=_JOB_ID),
    }

    released = find_goals_to_release_from_orphaned_jobs(
        session_ids=("s1", "s2", "s3"),
        goals_by_session=goals,
        orphaned_jobs=(_orphaned_job("s1"),),
    )

    assert released == ("goal-s1",)


@pytest.mark.asyncio
async def test_release_orphaned_wait_goals_updates_status() -> None:
    wait_goal = _goal(session_id="s1", status=GoalStatus.WAIT, wait_job_id=_JOB_ID)

    mock_store = MagicMock()
    mock_store.list_recent.return_value = [_orphaned_job("s1")]

    mock_storage = MagicMock()
    mock_storage.list_latest_goal_sessions = AsyncMock(return_value=["s1"])
    mock_storage.get_latest_goal_id = AsyncMock(return_value="goal-s1")
    mock_storage.get_goal = AsyncMock(return_value=wait_goal)
    mock_storage.save_goal = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.api.hooks.get_background_job_store",
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
            "app.services.agent.goals.unattended.publish_goal_needs_review_notification",
            new_callable=AsyncMock,
        ) as notify,
    ):
        from app.services.agent.goals.goal_wait_orphan_recovery import release_orphaned_wait_goals

        await release_orphaned_wait_goals()

    assert wait_goal.status == GoalStatus.NEEDS_HUMAN_REVIEW
    assert WAIT_ON_BACKGROUND_JOB_ID_KEY not in wait_goal.metadata
    mock_storage.save_goal.assert_awaited_once()
    notify.assert_awaited_once_with("s1", "goal-s1")
