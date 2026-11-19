"""Resume goals in WAIT when a linked background bash job finishes.

[INPUT]
- myrm_agent_harness.api.hooks::BackgroundJobFinishResult (POS: harness finish payload)
- app.services.agent.params.workspace_resolve::chat_id_from_session_id (POS: the chat a harness session key belongs to)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: the chat's goal provider, storage-backed between turns)
- app.services.agent.goals.unattended::trigger_goal_stream_with_failure_policy (POS: unattended headless stream + failure SSOT)

[OUTPUT]
- maybe_resume_goal_after_background_job: exit WAIT, trigger goal stream (or NEEDS_HUMAN_REVIEW on failure), return success flag

[POS]
Server-side companion to harness wait_background_bash auto-enter — closes the WAIT
barrier when the tracked background job exits and resumes autonomous execution. The harness reports the
session key of the run that started the job while the goal is stored under the chat, and the job ends between
turns, so the goal is looked up by chat through the registry's provider, which reads storage when no turn runs.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_JOB_ID_KEY
from myrm_agent_harness.api.hooks import BackgroundJobFinishResult

from app.services.agent.params.workspace_resolve import chat_id_from_session_id

logger = logging.getLogger(__name__)


async def maybe_resume_goal_after_background_job(result: BackgroundJobFinishResult) -> bool:
    """Exit WAIT and trigger unattended stream when the finished job matches wait job_id."""
    if not result.session_id or result.status != "exited" or not result.job_id:
        return False

    from app.services.agent.goals.goal_registry import GoalRegistry

    chat_id = chat_id_from_session_id(result.session_id)
    provider = GoalRegistry.resolve_provider(chat_id)

    goal = await provider.get_latest_goal(chat_id)
    if goal is None or goal.status != GoalStatus.WAIT:
        return False

    wait_job_id_raw = goal.metadata.get(WAIT_ON_BACKGROUND_JOB_ID_KEY)
    if wait_job_id_raw is None:
        return False

    wait_job_id = str(wait_job_id_raw).strip()
    if not wait_job_id or wait_job_id != result.job_id:
        return False

    await provider.exit_wait(goal.goal_id)
    refreshed = await provider.get_goal(goal.goal_id)
    if refreshed is None or refreshed.status != GoalStatus.ACTIVE:
        logger.warning(
            "Goal %s exit_wait did not reach ACTIVE after background job_id=%s finish",
            goal.goal_id,
            result.job_id,
        )
        return False

    logger.info(
        "Goal %s exited WAIT after background job_id=%s finished — triggering stream",
        goal.goal_id,
        result.job_id,
    )

    from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

    return await trigger_goal_stream_with_failure_policy(chat_id, refreshed, context="background wait resume")


__all__ = ["maybe_resume_goal_after_background_job"]
