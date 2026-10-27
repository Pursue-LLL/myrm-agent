"""The IM `/goal status` reply shows every part of a goal the user set, in a fixed order."""

from __future__ import annotations

from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus

from app.channels.i18n import get_text
from app.channels.types import InboundMessage
from app.core.channel_bridge.goal_handler.status_view import render_goal_status

_MSG = InboundMessage(channel="test", sender_id="user-1", content="/goal status")


def _goal(status: GoalStatus, **fields: object) -> Goal:
    return Goal(goal_id="g1", session_id="chat-1", objective="Ship the report", status=status, **fields)  # type: ignore[arg-type]


def test_a_bare_goal_shows_only_its_objective_and_status() -> None:
    reply = render_goal_status(_MSG, _goal(GoalStatus.PAUSED))

    assert reply.split("\n") == [
        get_text(_MSG, "goal_status_header", objective="Ship the report"),
        get_text(_MSG, "goal_status_line", status=get_text(_MSG, "goal_status_paused")),
    ]


def test_every_part_of_a_goal_follows_the_status_line_in_order() -> None:
    goal = _goal(
        GoalStatus.WAIT,
        budget=GoalBudget(max_tokens=1000, max_turns=5),
        tokens_used=10,
        turns_used=2,
        constraints=["no deploys"],
        acceptance_criteria=[{"type": "shell", "command": "pytest"}, {"type": "semantic", "criteria": "reads well"}],
        subgoals=[{"text": "draft"}, {"text": "review"}],
    )

    lines = render_goal_status(_MSG, goal).split("\n")

    budget_parts = " | ".join(
        [
            get_text(_MSG, "goal_budget_tokens", used=10, max=1000),
            get_text(_MSG, "goal_budget_turns", used=2, max=5),
        ]
    )
    assert lines[2:] == [
        get_text(_MSG, "goal_budget_header", parts=budget_parts),
        get_text(_MSG, "goal_status_constraints", items="no deploys"),
        get_text(_MSG, "goal_status_criteria", items="[shell] pytest | [semantic] reads well"),
        get_text(_MSG, "goal_status_subgoals", items="draft | review"),
    ]


def test_a_budget_without_limits_adds_no_budget_line() -> None:
    reply = render_goal_status(_MSG, _goal(GoalStatus.ACTIVE, budget=GoalBudget()))

    assert len(reply.split("\n")) == 2
