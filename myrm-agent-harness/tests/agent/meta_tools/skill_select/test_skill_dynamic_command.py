"""A skill's dynamic ``!`command``` is stopped at its deadline and keeps a bounded amount of its output."""

from __future__ import annotations

import asyncio
import time
import tracemalloc
from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent.meta_tools.skills.select import skill_document_loader
from myrm_agent_harness.agent.meta_tools.skills.select.skill_document_loader import _resolve_dynamic_context
from tests.support.marked_processes import kill_marked, process_alive

_FLOOD_MARKER = "skill_flood_4711"
_SLEEP_MARKER = "sleep 4752"


@pytest.fixture(autouse=True)
def _reap_command_processes() -> Iterator[None]:
    yield
    kill_marked(_FLOOD_MARKER)
    kill_marked(_SLEEP_MARKER)


@pytest.mark.asyncio
async def test_a_command_prints_its_output_into_the_document() -> None:
    assert await _resolve_dynamic_context("now: !`echo hello`") == "now: hello"


@pytest.mark.asyncio
async def test_output_longer_than_the_limit_is_cut_with_a_notice() -> None:
    document = await _resolve_dynamic_context("!`head -c 3000 /dev/zero | tr '\\0' x`")

    assert document == "x" * skill_document_loader._DYNAMIC_CMD_MAX_OUTPUT + "\n[output truncated]"


@pytest.mark.asyncio
async def test_a_failing_command_reports_what_it_wrote_to_stderr() -> None:
    document = await _resolve_dynamic_context("!`ls /nonexistent_path_4711`")

    assert document.startswith("[command failed: ") and "nonexistent_path_4711" in document


@pytest.mark.asyncio
async def test_a_command_that_runs_too_long_is_reported_and_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skill_document_loader, "_DYNAMIC_CMD_TIMEOUT", 1)

    document = await asyncio.wait_for(_resolve_dynamic_context("!`exec sleep 4752`"), timeout=15)

    assert document == "[command timed out after 1s]"
    assert not process_alive(_SLEEP_MARKER)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    ["sleep 4752; echo done", "sleep 4752 & echo started"],
    ids=["after_the_sleeper", "background_sleeper"],
)
async def test_a_command_is_stopped_at_its_deadline_together_with_everything_it_started(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setattr(skill_document_loader, "_DYNAMIC_CMD_TIMEOUT", 2)
    started = time.monotonic()

    document = await asyncio.wait_for(_resolve_dynamic_context(f"!`{command}`"), timeout=30)

    assert document == "[command timed out after 2s]"
    # Left running, what the command started keeps its pipes open and the loader waits out the whole drain period.
    assert time.monotonic() - started < 4.5
    assert not process_alive(_SLEEP_MARKER)


@pytest.mark.asyncio
async def test_a_command_that_never_stops_writing_is_stopped_at_its_deadline_without_filling_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_document_loader, "_DYNAMIC_CMD_TIMEOUT", 2)
    tracemalloc.start()
    tracemalloc.reset_peak()
    started = time.monotonic()
    try:
        document = await asyncio.wait_for(_resolve_dynamic_context(f"!`exec yes {_FLOOD_MARKER}`"), timeout=30)
        peak_bytes = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert document == "[command timed out after 2s]"
    assert time.monotonic() - started < 8
    assert not process_alive(_FLOOD_MARKER)
    # Without a cap the loader keeps every byte the command wrote during the two seconds (hundreds of MB).
    assert peak_bytes < 40 * 1024 * 1024
