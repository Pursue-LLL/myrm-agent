"""What each per-run guard remembers, and how a run opens, for tests of child-run isolation.

A child agent shares the context its parent's guards live in, so these tests compare what the guards hold
before and after a child ran. ``use_every_guard`` leaves a mark in every guard that a run's opening reset
clears in place; ``guard_state`` reads those marks back as one comparable value.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent._internals._agent_helpers import reset_all_guards
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import set_current_message_id
from myrm_agent_harness.agent.middlewares._session_context import get_terminal_errors
from myrm_agent_harness.agent.middlewares.completion import completion_guard_state as turn_state
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import get_loop_guard
from myrm_agent_harness.agent.security.guards.context_budget import get_context_budget_guard
from myrm_agent_harness.agent.security.guards.frequency_guard import get_frequency_guard
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord
from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import get_tool_turn_budget_guard

MESSAGE = "msg_1"
PARENT_TURN = "turn_parent"
CHILD_TURN = "turn_child"


@dataclass(frozen=True)
class GuardState:
    """What each per-run guard currently remembers, comparable across a child run."""

    tool_calls: int
    frequency_calls: int
    turn_budget_count: int
    context_tokens: int
    terminal_errors: frozenset[str]
    turn_refusals: int
    turn_forced_finish: bool
    turn_evidence: int
    turn_tier: dict[str, object] | None


def guard_state() -> GuardState:
    turn = turn_state.current_run_state()
    return GuardState(
        tool_calls=len(get_loop_guard()._window),
        frequency_calls=int(get_frequency_guard().get_stats()["current_window_size"]),
        turn_budget_count=get_tool_turn_budget_guard().check("web_search_tool", message_id=MESSAGE).tool_count,
        context_tokens=get_context_budget_guard().used_tokens,
        terminal_errors=frozenset(get_terminal_errors().get_all()),
        turn_refusals=turn.rejections,
        turn_forced_finish=turn.forced_finish,
        turn_evidence=len(turn.evidence),
        turn_tier=turn_state._run_disclosures.get(turn_state.run_key(), {}).get("deliverable_tier"),
    )


def use_every_guard(*, error: str) -> None:
    """What a run leaves behind in the guards: one tool call, one result, one error category, one refusal."""
    get_loop_guard().pre_check("file_write_tool", {"path": "app.py"})
    get_frequency_guard().record("file_write_tool")
    get_tool_turn_budget_guard().record("web_search_tool", message_id=MESSAGE)
    get_context_budget_guard().check_and_truncate("x" * 4_000, "bash_code_execute_tool")
    get_terminal_errors().add(error)
    turn = turn_state.current_run_state()
    turn.rejections += 1
    turn.forced_finish = True
    turn_state.record_evidence([CallRecord(tool_name="file_write_tool", args_hash=error, args={})])
    turn_state.publish_disclosure(deliverable_tier={"tier": error})


def start_run(*, turn: str, is_resume: bool = False) -> None:
    """What ``run_agent_loop`` opens a run with: reset the guards it finds, then bind the run's own turn."""
    reset_all_guards(is_resume=is_resume, graph_recursion_limit=100, unattended_mode=False)
    set_current_message_id(turn)


def turn_registries() -> tuple[frozenset[str], frozenset[str]]:
    """The turn ids the completion guard currently holds state and disclosure for."""
    return frozenset(turn_state._run_states), frozenset(turn_state._run_disclosures)
