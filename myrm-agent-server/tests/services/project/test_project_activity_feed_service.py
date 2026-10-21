"""Unit tests for ProjectActivityFeedService timeline aggregation.

[INPUT] Mock database session returning boards, tasks with handoffs, cron runs, milestones.
[OUTPUT] Validated ProjectActivityFeedResponse with chronological ordering and enriched metadata.
[POS] tests/services/project/test_project_activity_feed_service.py
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models.cron import CronRunModel
from app.database.models.kanban import KanbanTaskModel
from app.database.models.milestone import Milestone
from app.services.project.activity_feed_service import (
    ProjectActivityFeedService,
)


@pytest.mark.asyncio
async def test_project_activity_feed_aggregation() -> None:
    now = datetime.now(UTC)
    t_handoff = now - timedelta(minutes=10)
    t_completed = now - timedelta(minutes=5)
    t_cron = now - timedelta(minutes=2)
    t_milestone = now - timedelta(minutes=1)

    # 1. Mock Task with handoff history
    task1 = KanbanTaskModel(
        id="task-auth",
        board_id="board-proj-1",
        title="Implement OAuth2 Token Revocation",
        status="completed",
        agent_id="agent-developer",
        result="Tokens are properly invalidated on logout",
        metadata={
            "handoff_history": [
                {
                    "from_agent_id": "agent-architect",
                    "to_agent_id": "agent-developer",
                    "summary": "Architecture reviewed, ready for coding",
                    "changed_files": ["app/auth/router.py", "app/auth/service.py"],
                    "timestamp": t_handoff.isoformat(),
                }
            ]
        },
        updated_at=t_completed,
    )

    # 2. Mock Cron Run
    cron_run = CronRunModel(
        id="run-99",
        job_id="cron-job-1",
        status="ok",
        started_at=t_cron - timedelta(seconds=15),
        finished_at=t_cron,
        duration_ms=15200,
    )

    # 3. Mock Milestone
    milestone = Milestone(
        id="m-v1-beta",
        project_id="proj-test",
        title="Alpha Launch Milestone",
        description="Core multi-agent coordination verified",
        status="active",
        created_at=t_milestone,
    )

    # Set up mock execute results for the 5 SQL queries
    mock_boards_result = MagicMock()
    mock_boards_result.scalars.return_value.all.return_value = ["board-proj-1"]

    mock_tasks_result = MagicMock()
    mock_tasks_result.scalars.return_value.all.return_value = [task1]

    mock_cron_jobs_result = MagicMock()
    mock_cron_jobs_result.all.return_value = [("cron-job-1", "Nightly Code Health")]

    mock_cron_runs_result = MagicMock()
    mock_cron_runs_result.scalars.return_value.all.return_value = [cron_run]

    mock_milestones_result = MagicMock()
    mock_milestones_result.scalars.return_value.all.return_value = [milestone]

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [
        mock_boards_result,
        mock_tasks_result,
        mock_cron_jobs_result,
        mock_cron_runs_result,
        mock_milestones_result,
    ]

    @asynccontextmanager
    async def fake_get_session() -> AsyncIterator[AsyncMock]:
        yield mock_db

    with patch(
        "app.services.project.activity_feed_service.get_session",
        side_effect=fake_get_session,
    ):
        feed = await ProjectActivityFeedService.get_activity_feed(
            "proj-test",
            limit=20,
            offset=0,
        )

    assert feed.project_id == "proj-test"
    assert feed.total == 4
    assert len(feed.items) == 4

    # Verify descending chronological order: milestone (newest) -> cron_run -> task_completed -> task_handoff
    assert feed.items[0].kind == "milestone_created"
    assert feed.items[0].title == "Milestone added: Alpha Launch Milestone"

    assert feed.items[1].kind == "cron_run"
    assert feed.items[1].title == "Scheduled task run: Nightly Code Health"
    assert feed.items[1].metadata["status"] == "ok"

    assert feed.items[2].kind == "task_completed"
    assert feed.items[2].title == "Task completed: Implement OAuth2 Token Revocation"
    assert feed.items[2].actor == "agent-developer"

    assert feed.items[3].kind == "task_handoff"
    assert feed.items[3].title == "Task handed off: Implement OAuth2 Token Revocation"
    assert feed.items[3].metadata["from_agent_id"] == "agent-architect"
    assert feed.items[3].metadata["to_agent_id"] == "agent-developer"
    assert feed.items[3].metadata["changed_files"] == ["app/auth/router.py", "app/auth/service.py"]
