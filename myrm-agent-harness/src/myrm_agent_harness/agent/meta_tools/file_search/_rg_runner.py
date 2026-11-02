"""ripgrep subprocess runner shared by glob_tool and grep_tool.

[INPUT]
- asyncio::create_subprocess_exec (POS: async subprocess with pipe streams)

[OUTPUT]
- RgRunResult: exit code, stderr text and early-stop flag of one ripgrep run
- run_rg: Stream ripgrep stdout line by line with early stop, a bounded runtime and guaranteed reaping

[POS]
Owns the ripgrep process lifecycle for the file search tools. Both tools stop reading once they have
enough results; this module makes that early stop safe (no hang waiting for an exit that asyncio cannot
see) and releases the child on timeout or cancellation.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_DRAIN_CHUNK_BYTES = 65536
_REAP_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class RgRunResult:
    """Outcome of one ripgrep run."""

    returncode: int | None
    stderr: str
    stopped_early: bool

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


async def run_rg(
    cmd: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    on_line: Callable[[bytes], bool],
) -> RgRunResult:
    """Run ripgrep and feed each stdout line to ``on_line`` until it returns True (stop early).

    ``cwd`` is the search root: ripgrep anchors ``--glob`` patterns and prints relative paths against it.

    Raises:
        TimeoutError: ripgrep did not finish within ``timeout_seconds``; the process has been killed.
        RuntimeError: The subprocess pipes could not be created.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = proc.stdout, proc.stderr
    if stdout is None or stderr is None:
        await _reap(proc)
        raise RuntimeError("ripgrep pipes unavailable")

    stderr_data = bytearray()
    stopped_early = False

    async def _pump_stdout() -> None:
        nonlocal stopped_early
        while line := await stdout.readline():
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

    try:
        await asyncio.wait_for(
            asyncio.gather(_pump_stdout(), _pump_stderr(), proc.wait()),
            timeout=timeout_seconds,
        )
    except BaseException:
        await _reap(proc)
        raise

    return RgRunResult(
        returncode=proc.returncode,
        stderr=stderr_data.decode("utf-8", errors="replace"),
        stopped_early=stopped_early,
    )
