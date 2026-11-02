"""A test starts without the completion-guard turn state or disclosure the test before it left behind.

[INPUT]
- agent.middlewares.completion.completion_guard.state::publish_disclosure, pop_run_disclosure, current_run_state (POS: the registries the isolation fixture empties)
- agent.meta_tools.file_ops.observers.snapshot_observer::scoped_message_id (POS: binds a turn's message id)

[OUTPUT]
- TestGuardRegistriesBetweenTests: one chain, three tests, each of which must meet empty registries

[POS]
Pins ``_isolate_run_guard_registries`` through the behaviour it protects: the ``post_run_events`` call of one test
must not carry the ``deliverable_tier`` a guard test published with no message bound.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import scoped_message_id
from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import (
    UNBOUND_RUN_KEY,
    current_run_state,
    pop_run_disclosure,
    publish_disclosure,
)

_TURN = "turn-leaked"


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
