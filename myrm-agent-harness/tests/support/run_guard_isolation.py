"""Keep the per-run guard state a test leaves behind away from the next test (a pytest plugin).

[INPUT]
- agent.middlewares._session_context::isolated_terminal_errors (POS: the terminal-error registry, scoped by a ``with`` block)
- agent.middlewares.completion.completion_guard.state::_run_states / _run_disclosures (POS: the completion guard's turn state and
  disclosure payload, keyed by the bound message id, or by one shared slot when none is bound)
- agent.security.guards.context_budget::_budget_guard_var, agent.security.guards.tool_turn_budget_guard::_tool_turn_budget_guard_var
  (POS: the two budget guards a run counts its tool results and tool calls in, one per context)

[OUTPUT]
- _isolate_run_guard_registries: autouse fixture; every test starts, and ends, with these registries empty
- _budget_guards_stay_out_of_the_main_context: autouse fixture; a test that leaves a budget guard in the context it ran in errors at its own teardown
- held_budget_guards: the budget guards installed in the current context, ``None`` where there is none

[POS]
Registered from ``tests/conftest.py`` (``pytest_plugins``). A direct executor run never calls ``reset_all_guards``, so
what a test leaves in these registries stays in the worker process until another test reads it: a ``network_blocked``
makes the circuit breaker refuse the next test's MCP tool, and a disclosure published with no message bound lands on the
shared slot that the next ``post_run_events`` call attaches to its event. Which test ran before which depends on how
xdist hands out the classes, so without this the same code passes in one run and fails in the next.

The budget guards are not emptied between tests, because a run of a user installs none: each tool call of a graph run
creates its own in a copy of the context that is dropped afterwards, so a result meets an empty budget. A sync test that
asks for one (``get_context_budget_guard``) installs it in the context every later test of the worker starts from, where
the tool calls of later graph tests share it and count their results into it until it truncates each one to a stub.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from myrm_agent_harness.agent.security.guards.context_budget import ContextBudgetGuard
    from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import ToolTurnBudgetGuard


@pytest.fixture(autouse=True)
def _isolate_run_guard_registries() -> Iterator[None]:
    from myrm_agent_harness.agent.middlewares._session_context import isolated_terminal_errors
    from myrm_agent_harness.agent.middlewares.completion.completion_guard import state

    with (
        isolated_terminal_errors(),
        patch.dict(state._run_states, clear=True),
        patch.dict(state._run_disclosures, clear=True),
    ):
        yield


def held_budget_guards() -> tuple[ContextBudgetGuard | None, ToolTurnBudgetGuard | None]:
    """The context-budget and the tool-turn-budget guard installed in the current context; ``None`` for one not installed."""
    from myrm_agent_harness.agent.security.guards.context_budget import _budget_guard_var
    from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import _tool_turn_budget_guard_var

    return _budget_guard_var.get(None), _tool_turn_budget_guard_var.get(None)


@pytest.fixture(autouse=True)
def _budget_guards_stay_out_of_the_main_context() -> Iterator[None]:
    before = held_budget_guards()
    yield
    after = held_budget_guards()
    assert all(left is kept for left, kept in zip(after, before, strict=True)), (
        "the test left a context-budget or tool-turn-budget guard installed in the context it ran in; "
        "run the part that asks for one inside isolated_context_budget_guard() / isolated_tool_turn_budget_guard()"
    )
