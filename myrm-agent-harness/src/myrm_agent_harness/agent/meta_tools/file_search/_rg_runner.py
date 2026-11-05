"""ripgrep subprocess runner shared by glob_tool and grep_tool.

[INPUT]
- asyncio::create_subprocess_exec (POS: async subprocess with pipe streams)

[OUTPUT]
- RgRunResult: exit code, stderr text, early-stop flag and stdout line count of one ripgrep run
- run_rg: Stream ripgrep stdout lines (line feed or NUL ended) with early stop, bounded runtime and guaranteed reaping

[POS]
Owns the ripgrep process lifecycle for the file search tools. Both tools stop reading once they have
enough results; this module makes that early stop safe (no hang waiting for an exit that asyncio cannot
see), accepts the very long lines a match inside a minified file produces, and releases the child on
timeout, cancellation or a failing reader.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_DRAIN_CHUNK_BYTES = 65536
_REAP_TIMEOUT_SECONDS = 2.0
# ``rg --json`` puts a whole matching line into one event, so a hit inside a minified bundle or a lock file is a
# single line far above asyncio's 64 KiB default, which would abort the run. Lines beyond this still fail.
_STREAM_LIMIT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RgRunResult:
    """Outcome of one ripgrep run.

    ``lines_read`` counts the stdout lines handed to ``on_line``. A failed run that read none gave no answer (a
    pattern or a flag ripgrep rejects); one that read some searched on past an entry it could not open, so what
    it printed stands, an empty result included.
    """

    returncode: int | None
    stderr: str
    stopped_early: bool
    lines_read: int = 0

    @property
    def failed(self) -> bool:
        """True when ripgrep itself failed (exit code 2+), as opposed to 'no match' (1) or our own early stop."""
        return not self.stopped_early and self.returncode not in (0, 1)


async def _drain(stream: asyncio.StreamReader) -> None:
    while await stream.read(_DRAIN_CHUNK_BYTES):
        pass


async def _reap(proc: asyncio.subprocess.Process) -> None:
    """Kill a still-running ripgrep and release its pipes, never blocking the caller for long."""
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    streams = [stream for stream in (proc.stdout, proc.stderr) if stream is not None]
    with contextlib.suppress(TimeoutError, ProcessLookupError):
        await asyncio.wait_for(
            asyncio.gather(*(_drain(stream) for stream in streams), proc.wait()),
            timeout=_REAP_TIMEOUT_SECONDS,
        )


async def _read_line(stream: asyncio.StreamReader, terminator: bytes) -> bytes:
    """The next line with its terminator, empty at end of stream; the last line may lack one.

    ``StreamReader.readline`` for any terminator: a line beyond the stream limit raises ``ValueError``.
    """
    try:
        return await stream.readuntil(terminator)
    except asyncio.IncompleteReadError as incomplete:
        return incomplete.partial
    except asyncio.LimitOverrunError as overrun:
        raise ValueError(overrun.args[0]) from overrun


async def run_rg(
    cmd: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    on_line: Callable[[bytes], bool],
    line_terminator: bytes = b"\n",
) -> RgRunResult:
    """Run ripgrep and feed each stdout line to ``on_line`` until it returns True (stop early).

    ``cwd`` is the search root: ripgrep anchors ``--glob`` patterns and prints relative paths against it.
    A line ends at ``line_terminator`` and is passed on with it; ``--null`` output needs the NUL byte because a
    file name may itself hold a line feed.

    Raises:
        TimeoutError: ripgrep did not finish within ``timeout_seconds``; the process has been killed.
        ValueError: A stdout line exceeded ``_STREAM_LIMIT_BYTES``; the process has been killed.
        RuntimeError: The subprocess pipes could not be created.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=_STREAM_LIMIT_BYTES,
    )
    stdout, stderr = proc.stdout, proc.stderr
    if stdout is None or stderr is None:
        await _reap(proc)
        raise RuntimeError("ripgrep pipes unavailable")

    stderr_data = bytearray()
    stopped_early = False
    lines_read = 0

    async def _pump_stdout() -> None:
        nonlocal stopped_early, lines_read
        while line := await _read_line(stdout, line_terminator):
            lines_read += 1
            if on_line(line):
                stopped_early = True
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                # Output nobody reads keeps asyncio from observing end-of-stream, so proc.wait() would
                # stay pending until the timeout even though the process is already dead.
                await _drain(stdout)
                return

    async def _pump_stderr() -> None:
        while chunk := await stderr.read(4096):
            stderr_data.extend(chunk)

    pumps = [asyncio.ensure_future(work) for work in (_pump_stdout(), _pump_stderr(), proc.wait())]
    try:
        await asyncio.wait_for(asyncio.gather(*pumps), timeout=timeout_seconds)
    except BaseException:
        # gather leaves its siblings running when one of them fails; they must stop reading before _reap drains.
        for pump in pumps:
            pump.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)
        await _reap(proc)
        raise

    return RgRunResult(
        returncode=proc.returncode,
        stderr=stderr_data.decode("utf-8", errors="replace"),
        stopped_early=stopped_early,
        lines_read=lines_read,
    )
