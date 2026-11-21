"""A repeated read of a background job's output reuses the last view while the job prints nothing new.

Masking a window costs from a tenth of a second to half a second of CPU, and the activity panel reads a job that waits
for input every 3 s: a silent job is read again and again over the same lines.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import cast

import pytest

import myrm_agent_harness.agent.meta_tools.bash._background.output_window as window_module
from myrm_agent_harness.agent.meta_tools.bash._background.consume import BackgroundRegistryEntry
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES, OutputTail
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc, wait_until

_PID = 71001
_PRINTED = 50


@dataclass
class _QuietJob:
    """A job that printed ``line-1`` to ``line-50`` on stdout and is alive with both pipes open, waiting."""

    registry: BackgroundProcessRegistry
    pipe: FakeOutputPipe
    error_pipe: FakeOutputPipe

    async def print_line(self, text: str, *, to_stderr: bool = False) -> None:
        """The job prints one more line; returns once the reader has taken it."""
        entry = self.registry._entries[_PID]

        def printed() -> int:
            return entry.stderr_total if to_stderr else entry.stdout_total

        before = printed()
        (self.error_pipe if to_stderr else self.pipe).feed(f"{text}\n".encode())
        await wait_until(lambda: printed() == before + 1, what="the line to be read")


@pytest.fixture
async def quiet_job() -> AsyncIterator[_QuietJob]:
    registry = BackgroundProcessRegistry()
    pipe = FakeOutputPipe([f"line-{i}\n".encode() for i in range(1, _PRINTED + 1)], hold_open=True)
    error_pipe = FakeOutputPipe(hold_open=True)
    proc = FakeProc(pid=_PID, stdout=[], stdout_pipe=pipe, stderr_pipe=error_pipe)
    await registry.register(cast(AsyncProcessProtocol, proc), command="wait-for-input", session_id=None)
    await wait_until(lambda: registry._entries[_PID].stdout_total == _PRINTED, what="the lines to be read")
    yield _QuietJob(registry, pipe, error_pipe)
    proc.finish(0)
    await asyncio.sleep(0.05)


@pytest.fixture
def masked_windows(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The size of each window masked while a test runs: a read that masks both streams adds two entries."""
    sizes: list[int] = []
    original = window_module.redact_window

    def counting(lines: Sequence[str]) -> list[str]:
        sizes.append(len(lines))
        return original(lines)

    monkeypatch.setattr(window_module, "redact_window", counting)
    return sizes


@pytest.mark.asyncio
async def test_a_repeated_read_of_a_silent_job_masks_nothing_again(
    quiet_job: _QuietJob, masked_windows: list[int]
) -> None:
    first = quiet_job.registry.get_output(_PID, max_lines=10)
    masked_by_the_first = len(masked_windows)

    second = quiet_job.registry.get_output(_PID, max_lines=10)

    assert masked_by_the_first == 2
    assert len(masked_windows) == masked_by_the_first
    assert second == first


@pytest.mark.asyncio
@pytest.mark.parametrize("to_stderr", [False, True], ids=["stdout", "stderr"])
async def test_a_line_the_job_prints_ends_the_reuse(
    quiet_job: _QuietJob, masked_windows: list[int], to_stderr: bool
) -> None:
    quiet_job.registry.get_output(_PID, max_lines=10)
    masked_before = len(masked_windows)

    await quiet_job.print_line("one more", to_stderr=to_stderr)
    out = quiet_job.registry.get_output(_PID, max_lines=10)

    assert out["stderr" if to_stderr else "stdout"][-1] == "one more"
    assert len(masked_windows) == masked_before + 2


@pytest.mark.asyncio
async def test_another_number_of_lines_asked_for_is_not_served_from_the_last_view(quiet_job: _QuietJob) -> None:
    ten = quiet_job.registry.get_output(_PID, max_lines=10)
    five = quiet_job.registry.get_output(_PID, max_lines=5)

    assert ten["stdout"] == [f"line-{i}" for i in range(41, 51)]
    assert five["stdout"] == [f"line-{i}" for i in range(46, 51)]
    assert (ten.get("omitted_lines"), five.get("omitted_lines")) == (40, 45)


def _spoil(read: OutputTail) -> None:
    """What a caller may do with the result it got: empty a stream, flip a flag, drop a field."""
    read["stdout"].clear()
    read["dropped"] = True
    del read["omitted_lines"]


@pytest.mark.asyncio
@pytest.mark.parametrize("spoiled_reads", [1, 2], ids=["the_read_that_built_the_view", "a_read_that_reused_it"])
async def test_what_a_read_returns_is_the_callers_to_keep(quiet_job: _QuietJob, spoiled_reads: int) -> None:
    for _ in range(spoiled_reads):
        _spoil(quiet_job.registry.get_output(_PID, max_lines=10))

    again = quiet_job.registry.get_output(_PID, max_lines=10)

    assert again["stdout"] == [f"line-{i}" for i in range(41, 51)]
    assert again["dropped"] is False
    assert again.get("omitted_lines") == 40


class _RingTakingALineAfterTheCopy(deque[str]):
    """A ring that takes one more line, and counts it, right after a read has copied it.

    The reader task of a running job appends to a ring and then counts the line, without the registry's lock, so this
    can happen between any two steps of a read on another thread.
    """

    def __init__(self, entry: BackgroundRegistryEntry, lines: Iterable[str]) -> None:
        super().__init__(lines, maxlen=OUTPUT_RING_LINES)
        self._entry = entry
        self._armed = True

    def __iter__(self) -> Iterator[str]:
        yield from super().__iter__()
        if self._armed:
            self._armed = False
            self.append("late line")
            self._entry.stdout_total += 1


@pytest.mark.asyncio
async def test_a_line_that_lands_while_a_read_copies_the_ring_is_in_the_next_read(quiet_job: _QuietJob) -> None:
    entry = quiet_job.registry._entries[_PID]
    entry.stdout_buffer = _RingTakingALineAfterTheCopy(entry, entry.stdout_buffer)
    quiet_job.registry.get_output(_PID, max_lines=10)

    out = quiet_job.registry.get_output(_PID, max_lines=10)

    assert out["stdout"][-1] == "late line"
