"""Every reset a run opens with is accounted for in ``child_run_scope``.

``reset_all_guards`` is what a run does first, and it is the list ``child_run_scope`` has to answer: a guard it
clears in place would be cleared out from under the parent by a child's run, unless the scope hands the child
a guard of its own. The classification below is read against the functions themselves, so a reset added to
``reset_all_guards`` fails here until someone decides which kind it is, and an in-place one fails until the
child scope isolates it.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable

from myrm_agent_harness.agent._internals._agent_helpers import child_run_scope, reset_all_guards

# Clears state shared by every run of the process or the context, and the guard ``child_run_scope`` gives a child instead.
_RESET_IN_PLACE = {
    "reset_loop_guard": "child_loop_guard",
    "reset_frequency_guard": "isolated_frequency_guard",
    "reset_tool_turn_budget_guard": "isolated_tool_turn_budget_guard",
    "reset_context_budget_guard": "isolated_context_budget_guard",
    "reset_terminal_errors": "isolated_terminal_errors",
    "reset_completion_guard": "isolated_run_state",
}

# Binds a fresh object in the context the run executes in, so a run in its own task context leaves its parent's alone.
_RESET_REBINDING = frozenset(
    {
        "reset_replan_attempts",
        "reset_plan_confirm_state",
        "reset_denial_counter",
        "reset_taint_tracker",
        "reset_audit_log",
        "reset_privacy_tracker",
    }
)


def _calls_in(function: Callable[..., object]) -> list[ast.Call]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _name_of(call: ast.Call) -> str | None:
    return call.func.id if isinstance(call.func, ast.Name) else None


def test_every_reset_a_run_opens_with_is_classified() -> None:
    resets = {name for call in _calls_in(reset_all_guards) if (name := _name_of(call)) and name.startswith("reset_")}

    assert resets == set(_RESET_IN_PLACE) | _RESET_REBINDING


def test_every_reset_that_clears_in_place_has_its_isolated_counterpart_in_the_child_scope() -> None:
    entered = {
        name
        for call in _calls_in(child_run_scope)
        if isinstance(call.func, ast.Attribute) and call.func.attr == "enter_context"
        for argument in call.args
        if isinstance(argument, ast.Call) and (name := _name_of(argument))
    }

    assert entered - {"scoped_value"} == set(_RESET_IN_PLACE.values())
