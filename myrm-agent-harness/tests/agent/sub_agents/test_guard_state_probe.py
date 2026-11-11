"""The parent-run helper hands the run's terminal-error registry and budget guards back as it found them.

The circuit breaker refuses every network tool while ``network_blocked`` is registered, so a registry that outlives
the helper fails whichever test the same worker process runs next. A budget guard that outlives it is shared by the tool
calls of every later graph test of the worker, which count their results into it until it truncates each one to a stub.
"""

from __future__ import annotations

from myrm_agent_harness.agent.middlewares._session_context import get_terminal_errors
from tests.agent.sub_agents.guard_state_probe import parent_run_in_progress
from tests.support.run_guard_isolation import held_budget_guards


def test_a_parent_run_in_progress_leaves_no_terminal_error_behind() -> None:
    before = get_terminal_errors().get_all()

    with parent_run_in_progress():
        assert "network_blocked" in get_terminal_errors().get_all()

    assert get_terminal_errors().get_all() == before


def test_a_parent_run_in_progress_counts_in_budget_guards_of_its_own() -> None:
    before = held_budget_guards()

    with parent_run_in_progress():
        inside = held_budget_guards()

    assert all(guard is not None for guard in inside)
    assert all(own is not found for own, found in zip(inside, before, strict=True))
    assert all(after is found for after, found in zip(held_budget_guards(), before, strict=True))
