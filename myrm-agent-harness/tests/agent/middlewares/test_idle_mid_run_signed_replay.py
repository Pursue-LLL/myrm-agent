"""A slow tool in the middle of a run lets the prompt cache lapse, and the run keeps its reasoning all the same.

Once the cache is cold the pipeline is free to compact what is above its threshold, but a block signed earlier in the
run is bound to the messages compaction would rewrite, so the provider would refuse every block the run still replays.
These cases run the whole shipped stack against a provider double that enforces that binding, with the clock moved
past the five minutes Anthropic keeps a prompt cached while a tool runs.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::file_reader, run_signed_loop, signed_loop_session (POS: turns of the shipped agent in a tool loop against that double)
- tests.support.virtual_clock::virtual_clock, start_run (POS: an idle gap without the wait)

[POS]
Graph-level guard of the in-flight hold of compaction on a route that signs reasoning: a cold cache inside a run
compacts nothing, and the debt is paid when the next turn starts with no block in flight.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.signed_tool_loop import file_reader, run_signed_loop, signed_loop_session
from tests.support.virtual_clock import VirtualClock, start_run, virtual_clock

# Past the five minutes a prompt stays cached and short of the thirty an agent stays built for.
_IDLE_SECONDS = 400.0
# A window in which ten thousand characters of tool output a round carry the context past its compaction threshold
# within a dozen rounds, and short of the hard limit by the end of the run.
_WINDOW = 50_000
_ROUNDS = 18
_SLOW_CALL = 13


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
        yield


def _slow_reader(clock: VirtualClock) -> BaseTool:
    """A ``read_file`` that takes longer than the prompt cache lasts on its ``_SLOW_CALL``-th call."""
    return file_reader(10_000, on_call=lambda call: clock.advance(_IDLE_SECONDS) if call == _SLOW_CALL else None)


async def test_an_idle_gap_inside_a_run_compacts_nothing_and_keeps_its_reasoning() -> None:
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    with virtual_clock() as clock:
        start_run()
        await run_signed_loop(double, tools=[_slow_reader(clock)], turns=1, window=_WINDOW)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert double.shrinks == []


async def test_the_compaction_held_inside_a_run_is_paid_when_the_next_turn_starts() -> None:
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    with virtual_clock() as clock:

        def between_runs(turn: int) -> None:
            if turn > 1:
                clock.advance(_IDLE_SECONDS)
                double.tool_rounds = 2
            start_run()

        await run_signed_loop(double, tools=[_slow_reader(clock)], turns=2, window=_WINDOW, before_turn=between_runs)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    # Turn 1 makes a request for each round and one for the closing answer; the next turn's first request is the one
    # that shows the compacted history.
    assert double.shrinks == [_ROUNDS + 2]
