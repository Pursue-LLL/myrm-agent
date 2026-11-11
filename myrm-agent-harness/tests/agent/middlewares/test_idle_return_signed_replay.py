"""A run that starts after the prompt cache lapsed is shown the history it was shown before, so its reasoning is kept.

The pipeline prunes old tool results when the cache has gone cold. That view is rebuilt for each request, so a request
that prunes and the next one that no longer does are two different prompts under one signed block, and the provider
refuses it. These cases run the whole shipped stack against a provider double that enforces that binding, with the
clock moved past the five minutes Anthropic keeps a prompt cached.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::run_signed_loop, signed_loop_session (POS: turns of the shipped agent in a tool loop against that double)
- tests.support.virtual_clock::virtual_clock, start_run (POS: an idle gap without the wait)

[POS]
Graph-level guard of the cold-cache prune on a route that signs reasoning: an idle gap starts no prune, while a
window that is running out still does, and the one refusal that costs is healed by the replay guard.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest
from langchain_core.tools import tool

from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.signed_tool_loop import run_signed_loop, signed_loop_session
from tests.support.virtual_clock import start_run, virtual_clock

# Past the five minutes a prompt stays cached and short of the thirty an agent stays built for.
_IDLE_SECONDS = 400.0
_WINDOW = 60_000
_OUTPUT = ("line of tool output with distinct words alpha beta gamma delta epsilon zeta eta theta. " * 150)[:10_000]


@tool("read_file")
async def read_file(path: str) -> str:
    """Read a file."""
    return f"{path}\n{_OUTPUT}"


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
        yield


def _shrinks(double: EnforcingAnthropic) -> list[int]:
    """The requests that show the model less text than the request before them: something was pruned."""
    sizes = [len(record.text) for record in double.requests]
    return [number for number, (before, after) in enumerate(pairwise(sizes), start=1) if after < before]


async def test_a_run_after_an_idle_gap_prunes_nothing_and_keeps_its_reasoning() -> None:
    double = EnforcingAnthropic(tool_rounds=8)

    with virtual_clock() as clock:

        def between_runs(turn: int) -> None:
            if turn > 1:
                clock.advance(_IDLE_SECONDS)
            start_run()

        await run_signed_loop(double, tools=[read_file], turns=2, window=_WINDOW, before_turn=between_runs)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert _shrinks(double) == []


async def test_a_window_that_is_running_out_still_prunes_and_the_guard_heals_the_one_refusal() -> None:
    double = EnforcingAnthropic(tool_rounds=16)

    await run_signed_loop(double, tools=[read_file], turns=1, window=30_000)

    assert _shrinks(double)
    assert [record.reason for record in double.refused] == ["the prompt before the block changed"]
