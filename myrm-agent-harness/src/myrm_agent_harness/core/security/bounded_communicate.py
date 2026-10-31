"""Bounded collection of a child process's output.

``Process.communicate()`` keeps everything the child writes, so a command that prints without end (a retry loop
without a sleep, ``yes``, a listing of a whole disk) grows the host's memory for as long as it runs. This module
reads both pipes as ``communicate()`` does and keeps only the first ``max_bytes`` of each; the rest is read and
dropped, so the child never blocks on a full pipe.

[INPUT]
- none (standard library only)

[OUTPUT]
- BoundedOutput: the kept stdout and stderr, and whether either pipe wrote more than the cap
- communicate_bounded(): ``communicate()`` with a cap, whose deadline and cancel stop the process through the caller

[POS]
Output-bounding primitive for the commands the framework starts on its own (cron shell jobs, pre-flight probes).
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


async def communicate_bounded(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    on_abort: Callable[[], Awaitable[None]],
    max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> BoundedOutput:
    """Wait for *proc* to exit and return its output, at most *max_bytes* of each pipe.

    The deadline and a cancel run *on_abort* (which must stop the process and whatever it started), wait until the
    pipes close, and then raise ``TimeoutError`` or ``CancelledError``. The process must have been started with both
    stdout and stderr as pipes. ``proc.returncode`` is set when this returns.
    """
    if proc.stdout is None or proc.stderr is None:
        raise ValueError("communicate_bounded needs both stdout and stderr started as pipes")

    collecting = asyncio.ensure_future(
        asyncio.gather(_read_capped(proc.stdout, max_bytes), _read_capped(proc.stderr, max_bytes), proc.wait())
    )
    try:
        # The shield lets the readers outlive the deadline. They must keep emptying the pipes while on_abort runs: an
        # unread pipe fills and pauses the transport, and asyncio resolves ``wait()`` only after the pipes close,
        # so a process killed with its readers cancelled never reports its exit.
        (stdout, stdout_cut), (stderr, stderr_cut), _ = await asyncio.wait_for(asyncio.shield(collecting), timeout)
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
            collecting.cancel()
        raise

    truncated = stdout_cut or stderr_cut
    if truncated:
        logger.warning("Process %s wrote more than %d bytes to a pipe; the rest was discarded", proc.pid, max_bytes)
    return BoundedOutput(stdout=stdout, stderr=stderr, truncated=truncated)
