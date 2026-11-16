"""Unit tests for PTY background spawn helpers."""

from __future__ import annotations

import asyncio
import errno
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock

import psutil
import pytest

from myrm_agent_harness.toolkits.code_execution.executors.local._background_pty_spawn import (
    _PtyProcessWrapper,
    _PtyReaderProtocol,
    _PtyStdinWriter,
    pty_spawn_eligible,
    try_spawn_background_pty,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.utils import os_compat
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX pseudo-terminals")
_LOOP_HELD_S = 0.5
_HUP_IGNORING_JOB = "trap '' HUP; {sleeper} & wait"


async def _try_spawn(
    argv: list[str],
    *,
    effective_cwd: Path | None = None,
    preexec_fn: Callable[[], None] | None = None,
) -> AsyncProcessProtocol | None:
    return await try_spawn_background_pty(
        full_cmd_array=argv,
        effective_cwd=effective_cwd,
        env={"PATH": os.environ.get("PATH", os.defpath)},
        preexec_fn=preexec_fn,
        process_group_kwargs=os_compat.get_process_group_kwargs(),
    )


async def _spawn(argv: list[str], *, preexec_fn: Callable[[], None] | None = None) -> _PtyProcessWrapper:
    process = await _try_spawn(argv, preexec_fn=preexec_fn)
    assert isinstance(process, _PtyProcessWrapper)
    return process


async def _read_lines(process: _PtyProcessWrapper) -> list[bytes]:
    """Every line the job wrote, up to the clean end of stream that also closes the master descriptor."""
    lines: list[bytes] = []
    while line := await asyncio.wait_for(process.stdout.readline(), timeout=5):
        lines.append(line.strip())
    return lines


def test_pty_spawn_eligible_skips_sandbox_and_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    # Undone before the test returns: pytest builds paths for its report while a test's patches are still active, and
    # pathlib builds Windows paths while ``os.name`` is "nt", which aborts a verbose run started outside the rootdir.
    with monkeypatch.context() as patch:
        patch.setattr("os.name", "posix")
        assert pty_spawn_eligible(sandbox_enabled=False) is True
        assert pty_spawn_eligible(sandbox_enabled=True) is False
        patch.setattr("os.name", "nt")
        assert pty_spawn_eligible(sandbox_enabled=False) is False


def test_pty_stdin_writer_close_sends_one_eot() -> None:
    read_fd, write_fd = os.pipe()
    try:
        writer = _PtyStdinWriter(write_fd)
        writer.close()
        writer.close()
        payload = os.read(read_fd, 8)
        assert payload == b"\x04"
        with pytest.raises(BrokenPipeError):
            writer.write(b"x")
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_pty_process_wrapper_reuses_single_stdin_writer() -> None:
    proc = MagicMock()
    proc.pid = 123
    reader = MagicMock()
    wrapper = _PtyProcessWrapper(
        proc,
        master_fd=99,
        stdout_reader=reader,
        read_transport=MagicMock(),
        read_file=MagicMock(),
    )
    assert wrapper.stdin is wrapper.stdin


@pytest.mark.asyncio
async def test_pty_reader_protocol_keeps_buffered_lines_when_linux_reports_eio() -> None:
    """Linux fails the master read with EIO once the slave closes; buffered lines must still be delivered."""
    reader = asyncio.StreamReader()
    protocol = _PtyReaderProtocol(reader)
    reader.feed_data(b"line1\nline2\n")

    protocol.connection_lost(OSError(errno.EIO, "Input/output error"))

    assert await reader.readline() == b"line1\n"
    assert await reader.readline() == b"line2\n"
    assert await reader.readline() == b""


@pytest.mark.asyncio
async def test_pty_reader_protocol_still_surfaces_other_read_errors() -> None:
    reader = asyncio.StreamReader()
    protocol = _PtyReaderProtocol(reader)

    protocol.connection_lost(OSError(errno.EBADF, "Bad file descriptor"))

    with pytest.raises(OSError, match="Bad file descriptor"):
        await reader.readline()


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_spawned_pty_output_survives_child_exit() -> None:
    """Every line of a short-lived child is readable after it exits, followed by a clean EOF."""
    process = await _spawn([sys.executable, "-c", "print('one'); print('two'); print('three')"])
    await process.wait()

    assert await _read_lines(process) == [b"one", b"two", b"three"]


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_pty_job_has_no_separate_stderr_stream() -> None:
    """The PTY carries stdout and stderr as one stream, so the process exposes no stderr of its own."""
    process = await _spawn([sys.executable, "-c", "import sys; print('to-stderr', file=sys.stderr)"])

    assert process.stderr is None
    assert await _read_lines(process) == [b"to-stderr"]


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_stdin_reaches_the_job_and_closing_it_ends_the_input() -> None:
    """A line written to the master is what the job reads, and the EOT that ``close`` sends is its end of input."""
    process = await _spawn(
        [
            sys.executable,
            "-c",
            "import sys; print('got:' + sys.stdin.readline().strip()); print('eof:' + repr(sys.stdin.read()))",
        ]
    )

    process.stdin.write(b"abc\n")
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()
    # The terminal echoes what was typed, EOT included (``^D``), ahead of the job's own output, so the lines are
    # checked as one stream.
    output = b"\n".join(await _read_lines(process))

    assert await process.wait() == 0
    assert b"got:abc" in output
    assert output.endswith(b"eof:''")


@_POSIX_ONLY
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stop", "stop_signal"),
    [(_PtyProcessWrapper.terminate, signal.SIGTERM), (_PtyProcessWrapper.kill, signal.SIGKILL)],
    ids=["terminate", "kill"],
)
async def test_stopping_a_job_signals_every_process_in_its_group(
    stop: Callable[[_PtyProcessWrapper], None], stop_signal: signal.Signals
) -> None:
    sleeper = f"sleep 4762.{os.getpid():09d}"
    process = await _spawn(["/bin/sh", "-c", f"{sleeper} & wait"])
    try:
        await wait_until(lambda: process_alive(sleeper))

        stop(process)

        assert await asyncio.wait_for(process.wait(), timeout=5) == -stop_signal
        await wait_until(lambda: not process_alive(sleeper))
        await _read_lines(process)
    finally:
        kill_marked(sleeper)


def _restrict_umask() -> None:
    os.umask(0o027)


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_the_callers_preexec_hook_runs_in_the_job() -> None:
    process = await _spawn(["/bin/sh", "-c", "umask"], preexec_fn=_restrict_umask)

    assert [int(line, 8) for line in await _read_lines(process)] == [0o027]


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_host_without_pty_pairs_gets_no_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_pty_pair() -> tuple[int, int]:
        raise OSError(errno.ENOENT, "out of pseudo-terminals")

    monkeypatch.setattr("pty.openpty", no_pty_pair)

    assert await _try_spawn(["/bin/sh", "-c", "true"]) is None


def _held_while_the_child_runs_out(
    spawn: Callable[..., Awaitable[asyncio.subprocess.Process]],
) -> Callable[..., Awaitable[asyncio.subprocess.Process]]:
    """A spawn that returns late: the loop thread is held up, as on a loaded host, while its child runs to the end."""

    async def held(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        process = await spawn(*args, **kwargs)
        time.sleep(_LOOP_HELD_S)
        return process

    return held


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_spawned_pty_output_survives_a_child_that_finished_before_the_spawn_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A child that finished before the spawn returned leaves its output waiting for the master's reader.

    Closing the parent's slave descriptor then waits for that reader, and macOS discards the unread output once the
    wait runs out. The reader runs on the loop thread, so a close that blocks that thread loses the output of every
    job that finishes before the spawn returns.
    """
    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", _held_while_the_child_runs_out(asyncio.create_subprocess_exec)
    )
    process = await _spawn(["/bin/sh", "-c", "echo hello"])
    await process.wait()

    assert await _read_lines(process) == [b"hello"]


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_busy_default_executor_does_not_hold_a_spawn_up() -> None:
    """The slave is closed on a thread of its own: a spawn never waits for a worker of the shared default executor."""
    loop = asyncio.get_running_loop()
    release = threading.Event()
    default_pool_size = min(32, (os.cpu_count() or 1) + 4)
    blockers = [loop.run_in_executor(None, release.wait) for _ in range(default_pool_size)]
    try:
        process = await asyncio.wait_for(_spawn(["/bin/sh", "-c", "echo hello"]), timeout=5)

        assert await _read_lines(process) == [b"hello"]
    finally:
        release.set()
        await asyncio.gather(*blockers)


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_failed_pty_spawn_returns_none_and_leaves_no_descriptor_open(tmp_path: Path) -> None:
    open_before = psutil.Process().num_fds()

    process = await _try_spawn(["/bin/sh", "-c", "true"], effective_cwd=tmp_path / "missing")

    assert process is None
    assert psutil.Process().num_fds() <= open_before


def _failing_hook() -> None:
    raise RuntimeError("hook failed in the child")


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_spawn_that_raises_leaves_no_descriptor_open() -> None:
    """A hook that fails in the child surfaces as ``SubprocessError``; the PTY pair it was given must not outlive it."""
    open_before = psutil.Process().num_fds()

    with pytest.raises(subprocess.SubprocessError):
        await _try_spawn(["/bin/sh", "-c", "true"], preexec_fn=_failing_hook)

    assert psutil.Process().num_fds() <= open_before


async def _settle_after_a_failed_spawn(sleeper: str, open_before: int) -> None:
    """The job is gone once its group was signalled, yet what the loop and the reader hold for it closes a moment later.

    The loop closes the child's pidfd (Linux) and an attached reader's master only after it has seen the child exit,
    so the descriptor count settles shortly after the job is gone. A descriptor that is really leaked stays open.
    """
    await wait_until(lambda: not process_alive(sleeper), timeout=5)
    with suppress(TimeoutError):
        await wait_until(lambda: psutil.Process().num_fds() <= open_before, timeout=5)
    assert psutil.Process().num_fds() <= open_before


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_reader_that_fails_to_attach_does_not_leave_the_job_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the job runs and its reader cannot attach, no wrapper exists that could stop it, so the spawn must.

    A job that ignores SIGHUP (as ``nohup`` starts one) is not taken down by the hang-up of the closed master.
    """
    sleeper = f"sleep 4763.{os.getpid():09d}"

    async def cannot_attach(*args: object, **kwargs: object) -> None:
        await wait_until(lambda: process_alive(sleeper))
        raise OSError(errno.EBADF, "reader cannot attach")

    monkeypatch.setattr(asyncio.get_running_loop(), "connect_read_pipe", cannot_attach)
    open_before = psutil.Process().num_fds()
    try:
        with pytest.raises(OSError, match="reader cannot attach"):
            await _try_spawn(["/bin/sh", "-c", _HUP_IGNORING_JOB.format(sleeper=sleeper)])

        await _settle_after_a_failed_spawn(sleeper, open_before)
    finally:
        kill_marked(sleeper)


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_spawn_cancelled_while_its_reader_attaches_does_not_leave_the_job_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeper = f"sleep 4764.{os.getpid():09d}"
    job_running = asyncio.Event()

    async def attaches_for_ever(*args: object, **kwargs: object) -> None:
        await wait_until(lambda: process_alive(sleeper))
        job_running.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio.get_running_loop(), "connect_read_pipe", attaches_for_ever)
    open_before = psutil.Process().num_fds()
    spawn = asyncio.ensure_future(_try_spawn(["/bin/sh", "-c", _HUP_IGNORING_JOB.format(sleeper=sleeper)]))
    try:
        await asyncio.wait_for(job_running.wait(), timeout=10)
        spawn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await spawn

        await _settle_after_a_failed_spawn(sleeper, open_before)
    finally:
        kill_marked(sleeper)


@_POSIX_ONLY
@pytest.mark.asyncio
async def test_a_host_that_cannot_start_the_close_thread_does_not_leave_the_job_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container whose process limit is used up refuses the thread that closes the slave, after the job started."""
    sleeper = f"sleep 4766.{os.getpid():09d}"
    start_thread = threading.Thread.start

    def start(thread: threading.Thread) -> None:
        if thread.name != "pty-slave-close":
            start_thread(thread)
            return
        deadline = time.monotonic() + 10
        while not process_alive(sleeper) and time.monotonic() < deadline:
            time.sleep(0.02)
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", start)
    open_before = psutil.Process().num_fds()
    try:
        with pytest.raises(RuntimeError, match="can't start new thread"):
            await _try_spawn(["/bin/sh", "-c", _HUP_IGNORING_JOB.format(sleeper=sleeper)])

        await _settle_after_a_failed_spawn(sleeper, open_before)
    finally:
        kill_marked(sleeper)
