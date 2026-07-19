"""Resume goals in WAIT when a linked background bash job finishes.

[INPUT]
- myrm_agent_harness.api.hooks::BackgroundJobFinishResult (POS: harness finish payload)
- app.services.agent.goal_registry::GoalRegistry (POS: session GoalProvider lookup)
- app.services.agent.goal_stream_trigger::trigger_goal_stream (POS: unattended headless stream)

[OUTPUT]
- maybe_resume_goal_after_background_job: exit WAIT, trigger goal stream, return success flag

[POS]
Server-side companion to harness wait_background_bash auto-enter — closes the WAIT
barrier when the tracked background process exits and resumes autonomous execution.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_PID_KEY
from myrm_agent_harness.api.hooks import BackgroundJobFinishResult

logger = logging.getLogger(__name__)


async def maybe_resume_goal_after_background_job(result: BackgroundJobFinishResult) -> bool:
    """Exit WAIT and trigger unattended stream when the finished job matches wait pid."""
    if not result.session_id or result.status != "exited":
        return False

    from app.services.agent.goal_registry import GoalRegistry

    provider = GoalRegistry.get_provider(result.session_id)
    if provider is None:
        return False

    goal = await provider.get_latest_goal(result.session_id)
    if goal is None or goal.status != GoalStatus.WAIT:
        return False

    wait_pid_raw = goal.metadata.get(WAIT_ON_BACKGROUND_PID_KEY)
    if wait_pid_raw is None:
        return False

    try:
        wait_pid = int(wait_pid_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False

    if wait_pid != result.pid:
        return False

    if not hasattr(provider, "exit_wait"):
        return False

    await provider.exit_wait(goal.goal_id)
    refreshed = await provider.get_goal(goal.goal_id)
    if refreshed is None or refreshed.status != GoalStatus.ACTIVE:
        logger.warning(
            "Goal %s exit_wait did not reach ACTIVE after background pid=%s finish",
            goal.goal_id,
            result.pid,
        )
        return False

    logger.info(
        "Goal %s exited WAIT after background job pid=%s finished — triggering stream",
        goal.goal_id,
        result.pid,
    )

    try:
        from app.services.agent.goal_stream_trigger import trigger_goal_stream

        await trigger_goal_stream(result.session_id, refreshed)
    except Exception as exc:
        logger.error(
            "Failed to trigger stream after background wait resume goal=%s: %s",
            goal.goal_id,
            exc,
            exc_info=True,
        )
        return False

    return True


__all__ = ["maybe_resume_goal_after_background_job"]
