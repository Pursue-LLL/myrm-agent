"""communicate_bounded: communicate() with a cap, whose deadline and cancel stop the process and still return on time."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time

import pytest

from myrm_agent_harness.core.security import bounded_communicate
from myrm_agent_harness.core.security.bounded_communicate import communicate_bounded
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs

# Writes as fast as the pipe takes it, never exits on its own.
_FLOOD = "import sys\nwhile True:\n    sys.stdout.write('x' * 1023 + '\\n')\n"


async def _spawn(code: str, *, stdin: bool = False) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        stdin=asyncio.subprocess.PIPE if stdin else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **get_process_group_kwargs(),
    )


class _Abort:
    """An on_abort that kills the process and records whether it was still running when called."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc
        self.running_when_called: list[bool] = []

    async def __call__(self) -> None:
        self.running_when_called.append(self._proc.returncode is None)
        self._proc.kill()


@pytest.mark.asyncio
async def test_a_small_run_returns_what_communicate_returns() -> None:
    proc = await _spawn("import sys; sys.stdout.write('out'); sys.stderr.write('err'); sys.exit(3)")
    output = await communicate_bounded(proc, timeout=10, on_abort=_Abort(proc))
    assert (output.stdout, output.stderr, output.truncated, proc.returncode) == (b"out", b"err", False, 3)


@pytest.mark.asyncio
async def test_output_of_exactly_the_cap_is_not_truncated() -> None:
    proc = await _spawn("import sys; sys.stdout.write('a' * 1000)")
    output = await communicate_bounded(proc, timeout=10, on_abort=_Abort(proc), max_bytes=1000)
    assert output.stdout == b"a" * 1000
    assert output.truncated is False


@pytest.mark.asyncio
async def test_output_over_the_cap_keeps_the_head_and_the_child_still_finishes() -> None:
    # The child writes 3 MB and exits normally: it is never blocked on a full pipe, and what it said first is kept.
    proc = await _spawn("import sys; sys.stdout.write('h' * 1000 + 't' * 3_000_000)")
    output = await communicate_bounded(proc, timeout=20, on_abort=_Abort(proc), max_bytes=1000)
    assert output.stdout == b"h" * 1000
    assert output.truncated is True
    assert proc.returncode == 0


@pytest.mark.asyncio
async def test_each_pipe_has_its_own_cap() -> None:
    proc = await _spawn("import sys; sys.stdout.write('o' * 1500); sys.stderr.write('e' * 10)")
    output = await communicate_bounded(proc, timeout=10, on_abort=_Abort(proc), max_bytes=1000)
    assert (len(output.stdout), output.stderr, output.truncated) == (1000, b"e" * 10, True)


@pytest.mark.asyncio
async def test_a_deadline_stops_a_flooding_child_and_returns_on_time() -> None:
    proc = await _spawn(_FLOOD)
    abort = _Abort(proc)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        # The outer limit only bounds a hang; the elapsed check below tells it apart from the deadline.
        await asyncio.wait_for(communicate_bounded(proc, timeout=1, on_abort=abort), timeout=15)
    assert time.monotonic() - started < 6
    assert abort.running_when_called == [True]
    assert proc.returncode is not None


@pytest.mark.asyncio
async def test_a_cancel_stops_the_child_and_propagates() -> None:
    proc = await _spawn(_FLOOD)
    abort = _Abort(proc)
    task = asyncio.create_task(communicate_bounded(proc, timeout=60, on_abort=abort))
    await asyncio.sleep(0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=15)
    assert abort.running_when_called == [True]
    assert proc.returncode is not None


@pytest.mark.asyncio
async def test_a_descendant_holding_the_pipes_is_given_up_on(monkeypatch: pytest.MonkeyPatch) -> None:
    # on_abort kills only the process itself; its child keeps both pipes open, so they never reach EOF.
    monkeypatch.setattr(bounded_communicate, "_DRAIN_SECONDS", 0.5)
    code = "import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\ntime.sleep(30)\n"
    proc = await _spawn(code)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(communicate_bounded(proc, timeout=2, on_abort=_Abort(proc)), timeout=15)
        assert time.monotonic() - started < 6
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)


@pytest.mark.asyncio
async def test_a_process_without_both_pipes_is_refused() -> None:
    proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass", stdout=asyncio.subprocess.PIPE)
    try:
        with pytest.raises(ValueError, match="both stdout and stderr"):
            await communicate_bounded(proc, timeout=5, on_abort=_Abort(proc))
    finally:
        await proc.wait()


@pytest.mark.asyncio
async def test_stdin_data_is_fed_and_stdin_is_closed_so_the_child_sees_the_end() -> None:
    proc = await _spawn("import sys; sys.stdout.write(sys.stdin.read().upper())", stdin=True)
    output = await communicate_bounded(proc, timeout=10, on_abort=_Abort(proc), stdin_data=b"payload")
    assert output.stdout == b"PAYLOAD"


@pytest.mark.asyncio
async def test_a_payload_larger_than_the_pipes_is_fed_while_the_child_answers_it() -> None:
    # The child echoes while it reads. Feeding before reading, or the reverse, would deadlock on the full pipes.
    payload = bytes(range(256)) * 8192  # 2 MiB
    proc = await _spawn("import shutil, sys; shutil.copyfileobj(sys.stdin.buffer, sys.stdout.buffer)", stdin=True)
    output = await communicate_bounded(proc, timeout=20, on_abort=_Abort(proc), stdin_data=payload)
    assert output.stdout == payload
    assert output.truncated is False


@pytest.mark.asyncio
async def test_a_child_that_exits_without_reading_its_stdin_is_not_an_error() -> None:
    proc = await _spawn("pass", stdin=True)
    output = await communicate_bounded(proc, timeout=10, on_abort=_Abort(proc), stdin_data=b"x" * 2_000_000)
    assert (output.stdout, proc.returncode) == (b"", 0)


@pytest.mark.asyncio
async def test_a_deadline_stops_a_child_that_floods_and_never_reads_its_stdin() -> None:
    proc = await _spawn(_FLOOD, stdin=True)
    abort = _Abort(proc)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            communicate_bounded(proc, timeout=1, on_abort=abort, stdin_data=b"x" * 2_000_000), timeout=15
        )
    assert time.monotonic() - started < 6
    assert proc.returncode is not None


@pytest.mark.asyncio
async def test_stdin_data_without_a_stdin_pipe_is_refused() -> None:
    proc = await _spawn("pass")
    try:
        with pytest.raises(ValueError, match="stdin"):
            await communicate_bounded(proc, timeout=5, on_abort=_Abort(proc), stdin_data=b"x")
    finally:
        await proc.wait()
