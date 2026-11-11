"""A run whose tool results the pipeline would prune keeps its signed reasoning: the prune waits for the next turn.

The pipeline swaps old tool results for archive references to keep the context small. Every signed block of a turn is
bound to the results before it, so a prune in the middle of a run is a prompt the provider refuses, and the run then
reasons without its blocks for the rest of the turn. These cases run the whole shipped stack, archive included, against
a provider double that enforces that binding.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::file_reader, run_signed_loop, signed_loop_session (POS: turns of the shipped agent in a tool loop against that double)

[POS]
Graph-level guard of the per-step tool-result prune on a route that signs reasoning: a run of results big enough to be
pruned is never rewritten under its blocks, the turn after it starts from the pruned history, and a run that pauses for
an approval reads the same history after it resumes, also in a new agent and pipeline.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.signed_tool_loop import file_reader, run_signed_loop, signed_loop_session

_ROUNDS = 12
# Past the 2048 tokens the prune looks at, short of the 5000 the filter archives on arrival.
read_file = file_reader(16_000)


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
        yield


async def test_a_run_of_mid_size_results_keeps_its_reasoning_to_the_end() -> None:
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    await run_signed_loop(double, tools=[read_file], turns=1)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert double.shrinks == []


async def test_the_next_turn_starts_from_the_pruned_history_and_keeps_its_reasoning() -> None:
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    await run_signed_loop(double, tools=[read_file], turns=2)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert double.shrinks == [_ROUNDS + 2]


async def test_a_run_resumed_after_an_approval_still_reads_what_it_read_before_the_pause() -> None:
    # The second turn waits for an approval on its third read; the first turn made _ROUNDS reads.
    pausing = file_reader(16_000, pause_on_call=_ROUNDS + 3)
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    approvals = await run_signed_loop(double, tools=[pausing], turns=2)

    assert approvals == 1
    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert double.shrinks == [_ROUNDS + 2]
