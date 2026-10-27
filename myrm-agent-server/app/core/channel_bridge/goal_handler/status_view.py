"""Goal status card text for the IM ``/goal status`` reply.

[INPUT]
- myrm_agent_harness.agent.goals.types::Goal, GoalStatus (POS)
- app.channels.i18n::get_text, app.channels.types::InboundMessage (POS)

[OUTPUT]
- render_goal_status: the localized multi-line status reply for one goal

[POS]
Pure presentation of a goal for IM channels; the provider lookup stays in the handler.
"""

from __future__ import annotations

from myrm_agent_harness.agent.goals.types import Goal, GoalStatus

from app.channels.i18n import get_text
from app.channels.types import InboundMessage

_STATUS_KEYS: dict[GoalStatus, str] = {
    GoalStatus.QUEUED: "goal_status_queued",
    GoalStatus.ACTIVE: "goal_status_label",
    GoalStatus.PAUSED: "goal_status_paused",
    GoalStatus.PENDING_APPROVAL: "goal_status_pending_approval",
    GoalStatus.BUDGET_LIMITED: "goal_status_budget_limited",
    GoalStatus.WAIT: "goal_status_wait",
    GoalStatus.COMPLETE: "goal_status_complete",
    GoalStatus.CANCELLED: "goal_status_cancelled",
    GoalStatus.NEEDS_HUMAN_REVIEW: "goal_status_needs_review",
}


def render_goal_status(msg: InboundMessage, goal: Goal) -> str:
    status_key = _STATUS_KEYS.get(goal.status, "goal_status_label")
    label = get_text(msg, status_key)
    lines = [
        get_text(msg, "goal_status_header", objective=goal.objective),
        get_text(msg, "goal_status_line", status=label),
    ]

    if goal.budget:
        budget = goal.budget
        parts: list[str] = []
        if budget.max_tokens:
            parts.append(
                get_text(
                    msg,
                    "goal_budget_tokens",
                    used=goal.tokens_used or 0,
                    max=budget.max_tokens,
                )
            )
        if budget.max_turns:
            parts.append(
                get_text(
                    msg,
                    "goal_budget_turns",
                    used=goal.turns_used or 0,
                    max=budget.max_turns,
                )
            )
        if parts:
            lines.append(get_text(msg, "goal_budget_header", parts=" | ".join(parts)))

    if goal.constraints:
        lines.append(get_text(msg, "goal_status_constraints", items=" | ".join(goal.constraints)))

    if goal.acceptance_criteria:
        criteria_items: list[str] = []
        for ac in goal.acceptance_criteria:
            if ac.get("type") == "shell":
                criteria_items.append(f"[shell] {ac.get('command', '')}")
            else:
                criteria_items.append(f"[semantic] {ac.get('criteria', '')}")
        lines.append(get_text(msg, "goal_status_criteria", items=" | ".join(criteria_items)))

    if goal.subgoals:
        items = " | ".join(str(sg.get("text", "")) for sg in goal.subgoals)
        lines.append(get_text(msg, "goal_status_subgoals", items=items))

    return "\n".join(lines)
