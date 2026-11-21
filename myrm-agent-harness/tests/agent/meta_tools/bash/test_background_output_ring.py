"""The output ring of a background job: which lines ``output`` can return, when it reports ``dropped`` and how many
lines it leaves out (``omitted_lines``)."""

from __future__ import annotations

from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.output_window import WINDOW_MAX_CHARS, view_stream
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc, wait_until


def _lines(prefix: str, count: int) -> list[bytes]:
    return [f"{prefix}-{i}\n".encode() for i in range(1, count + 1)]


def _wide_lines(count: int) -> list[bytes]:
    """Lines of 1000 characters: 65 of them fill the window of a read, so only the newest ones can be shown."""
    return [f"{i:03d} ".encode() + b"x" * 996 + b"\n" for i in range(count)]


async def _produce(pid: int, *, stdout: list[bytes], stderr: list[bytes]) -> BackgroundProcessRegistry:
    """Run a job that prints the given lines and exits; return the registry once every line was read.

    The job has no session, so it has no spill log: the ring is the only place its lines go.
    """
    registry = BackgroundProcessRegistry()
    proc = FakeProc(pid=pid, stdout=stdout, stderr=stderr)
    await registry.register(cast(AsyncProcessProtocol, proc), command="generate", session_id=None)
    proc.finish(0)
    await wait_until(
        lambda: registry.get(pid) is not None and registry.get(pid).status == "exited",  # type: ignore[union-attr]
        what="the job to exit",
    )
    return registry


@pytest.mark.asyncio
async def test_a_ring_that_holds_every_line_is_not_dropped() -> None:
    registry = await _produce(70001, stdout=_lines("out", OUTPUT_RING_LINES), stderr=[])

    out = registry.get_output(70001, max_lines=OUTPUT_RING_LINES)

    assert len(out["stdout"]) == OUTPUT_RING_LINES
    assert out["dropped"] is False


@pytest.mark.asyncio
async def test_a_stream_past_the_ring_is_dropped_and_keeps_its_newest_lines() -> None:
    registry = await _produce(70002, stdout=_lines("out", OUTPUT_RING_LINES + 1), stderr=[])

    out = registry.get_output(70002, max_lines=OUTPUT_RING_LINES)

    stdout = out["stdout"]
    assert out["dropped"] is True
    assert len(stdout) == OUTPUT_RING_LINES
    assert stdout[0] == "out-2"
    assert stdout[-1] == f"out-{OUTPUT_RING_LINES + 1}"


@pytest.mark.asyncio
async def test_either_stream_past_the_ring_marks_the_output_dropped() -> None:
    registry = await _produce(70003, stdout=_lines("out", 3), stderr=_lines("err", OUTPUT_RING_LINES + 5))

    out = registry.get_output(70003, max_lines=OUTPUT_RING_LINES)

    assert out["dropped"] is True
    assert out["stdout"] == ["out-1", "out-2", "out-3"]


@pytest.mark.asyncio
async def test_a_busy_stream_does_not_evict_the_other_streams_lines() -> None:
    registry = await _produce(70004, stdout=_lines("out", 150), stderr=_lines("err", 100))

    out = registry.get_output(70004, max_lines=OUTPUT_RING_LINES)

    assert out["stdout"] == [f"out-{i}" for i in range(1, 151)]
    assert out["stderr"] == [f"err-{i}" for i in range(1, 101)]
    assert out["dropped"] is False


@pytest.mark.asyncio
async def test_asking_for_fewer_lines_is_not_a_drop() -> None:
    registry = await _produce(70005, stdout=_lines("out", 50), stderr=[])

    out = registry.get_output(70005, max_lines=5)

    assert out["stdout"] == [f"out-{i}" for i in range(46, 51)]
    assert out["dropped"] is False


@pytest.mark.asyncio
async def test_the_snapshot_tail_is_the_last_lines_of_each_stream() -> None:
    registry = await _produce(70006, stdout=_lines("out", 30), stderr=_lines("err", 2))

    info = registry.get(70006)

    assert info is not None
    assert info.last_stdout_tail == [f"out-{i}" for i in range(11, 31)]
    assert info.last_stderr_tail == ["err-1", "err-2"]


@pytest.mark.asyncio
async def test_a_stream_wider_than_the_window_shows_its_newest_lines_and_is_dropped() -> None:
    registry = await _produce(70007, stdout=_wide_lines(100), stderr=[])

    out = registry.get_output(70007, max_lines=OUTPUT_RING_LINES)

    stdout = out["stdout"]
    assert out["dropped"] is True
    assert sum(len(line) + 1 for line in stdout) <= WINDOW_MAX_CHARS
    assert stdout[-1].startswith("099 ")


@pytest.mark.asyncio
async def test_a_read_that_shows_every_line_leaves_none_out() -> None:
    registry = await _produce(70008, stdout=_lines("out", 50), stderr=_lines("err", 3))

    out = registry.get_output(70008, max_lines=OUTPUT_RING_LINES)

    assert "omitted_lines" not in out


@pytest.mark.asyncio
async def test_the_lines_older_than_the_ones_asked_for_are_left_out_without_a_drop() -> None:
    registry = await _produce(70009, stdout=_lines("out", 50), stderr=[])

    out = registry.get_output(70009, max_lines=5)

    assert out.get("omitted_lines") == 45
    assert out["dropped"] is False


@pytest.mark.asyncio
async def test_the_lines_that_fell_off_the_ring_are_left_out_with_the_ones_not_asked_for() -> None:
    registry = await _produce(70010, stdout=_lines("out", 300), stderr=[])

    assert registry.get_output(70010, max_lines=OUTPUT_RING_LINES).get("omitted_lines") == 100
    assert registry.get_output(70010, max_lines=50).get("omitted_lines") == 250


@pytest.mark.asyncio
async def test_each_stream_leaves_out_its_own_lines_and_the_counts_add_up() -> None:
    registry = await _produce(70011, stdout=_lines("out", 30), stderr=_lines("err", 250))

    out = registry.get_output(70011, max_lines=10)

    # stdout: 20 older than the 10 shown. stderr: 50 off the ring, then 190 older than the 10 shown.
    assert out.get("omitted_lines") == 20 + 50 + 190


@pytest.mark.asyncio
async def test_the_lines_a_cut_window_leaves_out_are_counted() -> None:
    registry = await _produce(70012, stdout=_wide_lines(100), stderr=[])

    out = registry.get_output(70012, max_lines=OUTPUT_RING_LINES)

    assert out.get("omitted_lines") == 100 - len(out["stdout"])


def test_a_count_that_trails_the_ring_leaves_no_negative_number_of_lines_out() -> None:
    """The reader task adds a line to a ring before it counts it, so a read on another thread can see one more."""
    view = view_stream(["a", "b", "c"], 2, OUTPUT_RING_LINES)

    assert view.lines == ["a", "b", "c"]
    assert view.omitted == 0
