"""Release goals stuck in WAIT when their background job was orphaned on restart.

[INPUT]
- myrm_agent_harness.agent.goals.storage::GoalStorage (POS: latest goal lookup)
- myrm_agent_harness.agent.meta_tools.bash._background_job_store (POS: orphaned job ledger)
- app.services.agent.goal_stream_trigger::publish_goal_needs_review_notification (POS: SSE)

[OUTPUT]
- release_orphaned_wait_goals: WAIT + orphaned background pid → NEEDS_HUMAN_REVIEW

[POS]
Server startup companion to pause_orphaned_active_goals — symmetric handling for WAIT barrier.
Must run after init_background_job_store() reconcile.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_PID_KEY

if TYPE_CHECKING:
    from myrm_agent_harness.api.hooks import BackgroundJobRecord

logger = logging.getLogger(__name__)

_REVIEW_REASON = "Background job lost after server restart — re-run the command to continue"


def _orphaned_jobs_by_session_pid(
    records: tuple[BackgroundJobRecord, ...],
) -> dict[tuple[str, int], BackgroundJobRecord]:
    indexed: dict[tuple[str, int], BackgroundJobRecord] = {}
    for record in records:
        if record.status != "orphaned" or record.pid is None:
            continue
        indexed[(record.session_id, record.pid)] = record
    return indexed


def _parse_wait_pid(goal: Goal) -> int | None:
    wait_pid_raw = goal.metadata.get(WAIT_ON_BACKGROUND_PID_KEY)
    if wait_pid_raw is None:
        return None
    try:
        return int(wait_pid_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def find_goals_to_release_from_orphaned_jobs(
    *,
    session_ids: tuple[str, ...],
    goals_by_session: dict[str, Goal | None],
    orphaned_jobs: tuple[BackgroundJobRecord, ...],
) -> tuple[str, ...]:
    """Return goal_ids that should exit WAIT because their background job was orphaned."""
    orphaned_index = _orphaned_jobs_by_session_pid(orphaned_jobs)
    if not orphaned_index:
        return ()

    to_release: list[str] = []
    for session_id in session_ids:
        goal = goals_by_session.get(session_id)
        if goal is None or goal.status != GoalStatus.WAIT:
            continue
        wait_pid = _parse_wait_pid(goal)
        if wait_pid is None:
            continue
        if (session_id, wait_pid) not in orphaned_index:
            continue
        to_release.append(goal.goal_id)
    return tuple(to_release)


async def release_orphaned_wait_goals() -> None:
    """Mark WAIT goals NEEDS_HUMAN_REVIEW when their tracked background job was orphaned."""
    from myrm_agent_harness.agent.goals.storage import GoalStorage
    from myrm_agent_harness.api.hooks import get_background_job_store
    from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

    store = get_background_job_store()
    if store is None:
        return

    orphaned_jobs = tuple(record for record in store.list_recent(limit=500) if record.status == "orphaned")
    if not orphaned_jobs:
        return

    storage = GoalStorage(get_storage_provider())
    session_ids = tuple(await storage.list_latest_goal_sessions())
    if not session_ids:
        return

    goals_by_session: dict[str, Goal | None] = {}
    for session_id in session_ids:
        goal_id = await storage.get_latest_goal_id(session_id)
        if not goal_id:
            goals_by_session[session_id] = None
            continue
        goals_by_session[session_id] = await storage.get_goal(goal_id)

    goal_ids = find_goals_to_release_from_orphaned_jobs(
        session_ids=session_ids,
        goals_by_session=goals_by_session,
        orphaned_jobs=orphaned_jobs,
    )
    if not goal_ids:
        return

    from app.services.agent.goal_stream_trigger import publish_goal_needs_review_notification

    released = 0
    for session_id, goal in goals_by_session.items():
        if goal is None or goal.goal_id not in goal_ids:
            continue

        goal.status = GoalStatus.NEEDS_HUMAN_REVIEW
        goal.metadata.pop(WAIT_ON_BACKGROUND_PID_KEY, None)
        goal.metadata.pop("wait_reason", None)
        goal.metadata.pop("wait_started_at", None)
        goal.metadata.pop("wait_max_seconds", None)
        goal.metadata["review_reason"] = _REVIEW_REASON
        await storage.save_goal(goal)
        await publish_goal_needs_review_notification(session_id, goal.goal_id)
        released += 1
        logger.info(
            "Goal %s (session %s) released from WAIT — background job orphaned after restart",
            goal.goal_id,
            session_id,
        )

    if released:
        logger.info("Released %d goal(s) from orphaned WAIT after server restart", released)


__all__ = [
    "find_goals_to_release_from_orphaned_jobs",
    "release_orphaned_wait_goals",
]
