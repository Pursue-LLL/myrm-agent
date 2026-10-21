"""``on_goal_hold`` callback: server-side effects once the harness has parked a goal.

[INPUT]
- myrm_agent_harness.api.hooks::ProviderWindowHint (POS: provider-stated retry boundary)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: session GoalProvider)
- app.services.agent.goals.usage_limit_resume.daemon (POS: armed wake set, ownership stamp)
- app.services.agent.goals.usage_limit_resume.notify (POS: user notification)

[OUTPUT]
- build_goal_hold_callback: callback injected into the stream context next to ``on_loop_restart``

[POS]
The harness decides to hold or pause; this callback only makes the hold real on the host: stamp the
goal as daemon-owned, arm the wake daemon, tell the user. Only a goal the harness actually parks reaches
this callback, and parking needs two things. The stream context must carry ``goal_provider``: the session
orchestrator and the unattended goal streams write it, IM channel turns do not, so a usage-limit error
there takes the regular error-reply path. The goal must also be stored under the stream's session key.
Kanban goals are not and Cron runs carry no ``goal_provider``, so both are rescheduled by their own
scheduler instead.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.api.hooks import ProviderWindowHint

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.usage_limit_resume.daemon import WAKE_OWNER, WAKE_OWNER_KEY, get_usage_limit_wake_daemon
from app.services.agent.goals.usage_limit_resume.notify import publish_goal_usage_limit_notification


def build_goal_hold_callback() -> Callable[[Goal, ProviderWindowHint], Awaitable[None]]:
    async def _on_goal_hold(goal: Goal, hint: ProviderWindowHint) -> None:
        if goal.status is not GoalStatus.WAIT:
            await publish_goal_usage_limit_notification(goal.session_id, goal.goal_id, "paused")
            return
        provider = GoalRegistry.get_or_create_provider(goal.session_id)
        await provider.update_metadata(goal.goal_id, {WAKE_OWNER_KEY: WAKE_OWNER})
        get_usage_limit_wake_daemon().arm(goal.session_id, hint.reset_at)
        await publish_goal_usage_limit_notification(goal.session_id, goal.goal_id, "wait")

    return _on_goal_hold
