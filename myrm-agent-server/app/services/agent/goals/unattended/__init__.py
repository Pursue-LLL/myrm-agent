"""Unattended goal turns: the headless stream the server starts for a goal and what a failed start leaves behind (facade).

[INPUT]
- .trigger / .failure (POS: headless goal stream, failure policy)

[OUTPUT]
- GoalStreamAgentContext, trigger_goal_stream, trigger_goal_stream_with_failure_policy
- TriggerFailurePolicy, handle_unattended_goal_stream_failure, publish_goal_needs_review_notification, resolve_user_locale

[POS]
The one import point for goal resume, follow-up turns, wake after a background job and orphan recovery.
"""

from app.services.agent.goals.unattended.failure import (
    TriggerFailurePolicy,
    handle_unattended_goal_stream_failure,
    publish_goal_needs_review_notification,
    resolve_user_locale,
)
from app.services.agent.goals.unattended.trigger import (
    GoalStreamAgentContext,
    trigger_goal_stream,
    trigger_goal_stream_with_failure_policy,
)

__all__ = [
    "GoalStreamAgentContext",
    "TriggerFailurePolicy",
    "handle_unattended_goal_stream_failure",
    "publish_goal_needs_review_notification",
    "resolve_user_locale",
    "trigger_goal_stream",
    "trigger_goal_stream_with_failure_policy",
]
