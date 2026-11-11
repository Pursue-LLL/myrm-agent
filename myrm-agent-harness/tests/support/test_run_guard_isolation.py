"""A test starts without the per-run guard state the test before it left behind.

[INPUT]
- agent.middlewares.completion.completion_guard.state::publish_disclosure, pop_run_disclosure, current_run_state (POS: the registries the isolation fixture empties)
- agent.meta_tools.file_ops.observers.snapshot_observer::scoped_message_id (POS: binds a turn's message id)
- tests.support.run_guard_isolation (POS: the plugin whose budget-guard check an inner pytest session loads)

[OUTPUT]
- TestGuardRegistriesBetweenTests: one chain, three tests, each of which must meet empty registries
- test_a_test_that_leaves_a_budget_guard_behind_errors_at_its_own_teardown: the check that keeps a budget guard out of the
  context every later test of the worker starts from

[POS]
Pins ``_isolate_run_guard_registries`` through the behaviour it protects: the ``post_run_events`` call of one test
must not carry the ``deliverable_tier`` a guard test published with no message bound. Pins
``_budget_guards_stay_out_of_the_main_context`` on an inner session, whose process the guard it catches cannot leak out of.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import scoped_message_id
from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import (
    UNBOUND_RUN_KEY,
    current_run_state,
    pop_run_disclosure,
    publish_disclosure,
)

_TURN = "turn-leaked"
_HARNESS_ROOT = Path(__file__).resolve().parents[2]
_BUDGET_GUARD_TESTS = """
from myrm_agent_harness.agent.security.guards.context_budget import (
    get_context_budget_guard,
    isolated_context_budget_guard,
)


def test_scopes_the_guard_it_asks_for():
    with isolated_context_budget_guard():
        get_context_budget_guard()


def test_leaves_the_guard_it_asks_for_in_the_context():
    get_context_budget_guard()
"""


def _nothing_left_behind() -> None:
    assert pop_run_disclosure(UNBOUND_RUN_KEY) is None
    assert pop_run_disclosure(_TURN) is None
    assert current_run_state().rejections == 0
    with scoped_message_id(_TURN):
        assert current_run_state().rejections == 0


class TestGuardRegistriesBetweenTests:
    """The three tests are one chain and only mean something in file order, which pytest keeps: the first leaves a
    disclosure and a rejection count on the unbound slot and on a bound turn, the two after it must not meet them."""

    def test_a_sync_test_leaves_state_on_the_unbound_slot_and_on_a_turn(self) -> None:
        publish_disclosure(deliverable_tier={"tier": "claimed"})
        current_run_state().rejections = 2
        with scoped_message_id(_TURN):
            publish_disclosure(staged_artifacts=[{"path": "draft.md"}])
            current_run_state().rejections = 2

    @pytest.mark.asyncio
    async def test_an_async_test_after_it_starts_empty(self) -> None:
        _nothing_left_behind()
        publish_disclosure(deliverable_tier={"tier": "claimed"})

    def test_a_sync_test_after_that_starts_empty(self) -> None:
        _nothing_left_behind()


def test_a_test_that_leaves_a_budget_guard_behind_errors_at_its_own_teardown(tmp_path: Path) -> None:
    session = tmp_path / "test_budget_guards.py"
    session.write_text(_BUDGET_GUARD_TESTS)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.support.run_guard_isolation",
            "-p",
            "no:cacheprovider",
            "-q",
            str(session),
        ],
        cwd=_HARNESS_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert "2 passed, 1 error" in result.stdout, result.stdout
    assert re.search(rf"^ERROR .*{session.name}::test_leaves_the_guard_it_asks_for_in_the_context", result.stdout, re.M)
    assert "left a context-budget or tool-turn-budget guard" in result.stdout
