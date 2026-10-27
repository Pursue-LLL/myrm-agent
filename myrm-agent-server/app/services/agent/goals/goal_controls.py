"""Goal controls shared by the HTTP API and IM commands.

[INPUT]
- myrm_agent_harness.agent.goals.protocols::GoalProvider (POS: Goal persistence and lifecycle)
- app.services.agent.gateway::get_agent_gateway (POS: in-flight session and drain state)
- app.services.agent.goals.goal_stream_trigger::trigger_goal_stream_with_failure_policy (POS: unattended goal continuation stream)

[OUTPUT]
- NON_TERMINAL_GOAL_STATUSES: statuses a goal can still leave
- select_cancellable_goal: the goal a "cancel" / "clear" control acts on
- continue_resumed_goal: start the turn that carries a just-resumed goal forward

[POS]
One rule per control, so the web card and the IM command agree on which goal they act on and
a resume actually puts the goal back to work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.goal_stream_trigger import trigger_goal_stream_with_failure_policy

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.agent.goals.types import Goal

NON_TERMINAL_GOAL_STATUSES: frozenset[GoalStatus] = frozenset(
    {
        GoalStatus.ACTIVE,
        GoalStatus.PAUSED,
        GoalStatus.PENDING_APPROVAL,
        GoalStatus.BUDGET_LIMITED,
        GoalStatus.NEEDS_HUMAN_REVIEW,
        GoalStatus.QUEUED,
        GoalStatus.WAIT,
    }
)


async def select_cancellable_goal(provider: GoalProvider, session_id: str) -> Goal | None:
    """The running goal, else the latest goal while it is still open (paused, in review, waiting, ...)."""
    active = await provider.get_active_goal(session_id)
    if active is not None:
        return active
    latest = await provider.get_latest_goal(session_id)
    if latest is not None and latest.status in NON_TERMINAL_GOAL_STATUSES:
        return latest
    return None


async def continue_resumed_goal(session_id: str, provider: GoalProvider, goal_id: str) -> bool:
    """Start the unattended turn for a goal that was just resumed.

    False when nothing was started: the session is busy or the app is draining (the running turn or the
    next message carries the goal on), or the goal is not active.
    """
    gateway = get_agent_gateway()
    if gateway.is_draining or gateway.is_session_active(session_id):
        return False
    goal = await provider.get_goal(goal_id)
    if goal is None or goal.status is not GoalStatus.ACTIVE:
        return False
    return await trigger_goal_stream_with_failure_policy(
        session_id, goal, provider, on_failure="needs_human_review", context="goal resume"
    )
