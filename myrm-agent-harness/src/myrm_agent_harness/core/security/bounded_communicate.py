"""Bounded collection of a child process's output.

``Process.communicate()`` keeps everything the child writes, so a command that prints without end (a retry loop
without a sleep, ``yes``, a listing of a whole disk) grows the host's memory for as long as it runs. This module
reads both pipes as ``communicate()`` does and keeps only the first ``max_bytes`` of each (stderr may have its own
cap); the rest is read and dropped, so the child never blocks on a full pipe. Bytes for the child's stdin are fed alongside, as ``communicate()``
feeds them.

[INPUT]
- none (standard library only)

[OUTPUT]
- BoundedOutput: the kept stdout and stderr, and whether either pipe wrote more than the cap
- communicate_bounded(): ``communicate()`` with a cap (stderr may have its own), whose deadline and cancel stop the process through the caller
- DEFAULT_MAX_OUTPUT_BYTES: the cap per pipe when the caller names none

[POS]
Output-bounding primitive for every command whose text or output size the framework does not control (cron shell
jobs, pre-flight probes, agent Python scripts, command hooks, skill dynamic commands, remote SSH commands).
It stops the process only through the ``on_abort`` it is given: how a tree dies differs by caller.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_MAX_OUTPUT_BYTES = 5 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
# Once on_abort has run, the pipes close within moments unless something that escaped the kill still holds them.
_DRAIN_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class BoundedOutput:
    """What a child wrote: at most the cap per pipe, and whether either pipe wrote more than that."""

    stdout: bytes
    stderr: bytes
    truncated: bool


async def _read_capped(stream: asyncio.StreamReader, max_bytes: int) -> tuple[bytes, bool]:
    """Read *stream* to EOF, keeping its first *max_bytes*; returns them and whether more was written."""
    kept = bytearray()
    truncated = False
    while chunk := await stream.read(_READ_CHUNK_BYTES):
        room = max_bytes - len(kept)
        if len(chunk) > room:
            truncated = True
        if room > 0:
            kept += chunk[:room]
    return bytes(kept), truncated


def _mark_outcome_retrieved[T](collection: asyncio.Future[T]) -> None:
    """Retrieve the outcome of a collection nobody awaits any more, so asyncio does not log it as never retrieved.

    A cancelled gather ends with a CancelledError set on it rather than a cancelled state; the caller re-raises the
    TimeoutError or CancelledError that made it give up, so nothing else is owed this outcome.
    """
    if not collection.cancelled():
        collection.exception()


async def _feed_stdin(stdin: asyncio.StreamWriter | None, data: bytes | None) -> None:
    """Write *data* to *stdin* and close it. A child that stops reading, or exits, is not an error."""
    if stdin is None or data is None:
        return
    try:
        stdin.write(data)
        await stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        stdin.close()


async def communicate_bounded(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    on_abort: Callable[[], Awaitable[None]],
    max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    stderr_max_bytes: int | None = None,
    stdin_data: bytes | None = None,
) -> BoundedOutput:
    """Wait for *proc* to exit and return its output, at most *max_bytes* of stdout and *stderr_max_bytes* of stderr.

    *stderr_max_bytes* defaults to *max_bytes*; a caller whose stdout carries an encoded result passes a smaller one,
    because stderr is raw text and needs no such room.

    The deadline and a cancel run *on_abort* (which must stop the process and whatever it started), wait until the
    pipes close, and then raise ``TimeoutError`` or ``CancelledError``. The process must have been started with both
    stdout and stderr as pipes, and with stdin as a pipe when *stdin_data* is given (it is written, then stdin is
    closed). ``proc.returncode`` is set when this returns.
    """
    if proc.stdout is None or proc.stderr is None:
        raise ValueError("communicate_bounded needs both stdout and stderr started as pipes")
    if stdin_data is not None and proc.stdin is None:
        raise ValueError("communicate_bounded needs stdin started as a pipe to feed stdin_data")

    stderr_cap = max_bytes if stderr_max_bytes is None else stderr_max_bytes
    collecting = asyncio.ensure_future(
        asyncio.gather(
            _read_capped(proc.stdout, max_bytes),
            _read_capped(proc.stderr, stderr_cap),
            proc.wait(),
            _feed_stdin(proc.stdin, stdin_data),
        )
    )
    try:
        # The shield lets the readers outlive the deadline. They must keep emptying the pipes while on_abort runs: an
        # unread pipe fills and pauses the transport, and asyncio resolves ``wait()`` only after the pipes close,
        # so a process killed with its readers cancelled never reports its exit.
        (stdout, stdout_cut), (stderr, stderr_cut), _, _ = await asyncio.wait_for(asyncio.shield(collecting), timeout)
    except BaseException:
        try:
            await asyncio.shield(on_abort())
            done, _ = await asyncio.wait({collecting}, timeout=_DRAIN_SECONDS)
            if not done:
                logger.warning(
                    "Pipes of process %s still open %.0fs after it was stopped; something it started holds them",
                    proc.pid,
                    _DRAIN_SECONDS,
                )
        finally:
            collecting.add_done_callback(_mark_outcome_retrieved)
            collecting.cancel()
        raise

    cut_pipes = [name for name, was_cut in (("stdout", stdout_cut), ("stderr", stderr_cut)) if was_cut]
    if cut_pipes:
        logger.warning(
            "Process %s wrote past its cap on %s (stdout cap %d bytes, stderr cap %d bytes); the rest was discarded",
            proc.pid,
            " and ".join(cut_pipes),
            max_bytes,
            stderr_cap,
        )
    return BoundedOutput(stdout=stdout, stderr=stderr, truncated=bool(cut_pipes))
