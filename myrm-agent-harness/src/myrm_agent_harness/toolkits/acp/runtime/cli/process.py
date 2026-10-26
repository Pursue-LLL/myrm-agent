"""A spawned CLI agent process — line-wise stdout, a bounded stderr tail, and the only code that stops it.

Every way a turn can end (EOF, an error, a cancelled task, an abandoned stream, a timeout) leaves through the
``spawn_cli_process`` context, which stops a process that is still running. Stopping is idempotent and runs to
completion even when the task awaiting it is cancelled again, so a stopped turn never leaves a CLI behind.

[INPUT]
- utils.os_compat::get_process_group_kwargs, kill_process_group (POS: Unified abstractions for POSIX/Windows differences (file locks, process groups))

[OUTPUT]
- CliProcess: a running CLI process with ``lines``, ``wait``, ``terminate`` and the facts a turn is judged by
- spawn_cli_process: async context manager that spawns a CliProcess and stops it on exit

[POS]
Process ownership of CliRuntime. Knows nothing about the CLI's output format or sessions.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.utils.os_compat import get_process_group_kwargs, kill_process_group

logger = logging.getLogger(__name__)

# One NDJSON line can carry a whole file (a tool result), far past asyncio's 64 KiB default line limit.
_STDOUT_LINE_LIMIT = 16 * 1024 * 1024
_STDERR_TAIL_BYTES = 8 * 1024
_STDERR_READ_BYTES = 4096
_TERMINATE_GRACE_SECONDS = 5.0
# A grandchild that inherited the pipe can keep stderr open after the CLI exited; the tail is enough by then.
_STDERR_DRAIN_SECONDS = 2.0
_KILL = getattr(signal, "SIGKILL", signal.SIGTERM)


def _signal_group(pid: int, sig: int) -> None:
    try:
        kill_process_group(pid, sig)
    except OSError:
        logger.debug("cli_process_signal_failed pid=%d signal=%d", pid, sig, exc_info=True)


class CliProcess:
    """One running CLI process and its pipes."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._stderr_tail = b""
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        self._termination: asyncio.Future[None] | None = None
        self._killed_by_us = False

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    @property
    def killed_by_us(self) -> bool:
        """Whether this runtime stopped the process while it was still running (cancel, timeout, shutdown)."""
        return self._killed_by_us

    @property
    def stderr_text(self) -> str:
        """The last few KiB the process wrote to stderr."""
        return self._stderr_tail.decode("utf-8", errors="replace").strip()

    async def send_prompt(self, text: str) -> None:
        """Write ``text`` to stdin and close it; a process that already left is not an error here."""
        stdin = self._process.stdin
        if stdin is None:
            return
        try:
            stdin.write(text.encode("utf-8") + b"\n")
            await stdin.drain()
            stdin.close()
            await stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("cli_process_left_before_prompt pid=%d", self._process.pid)

    async def lines(self) -> AsyncIterator[str]:
        """Non-empty stdout lines until the process closes its stdout."""
        stdout = self._process.stdout
        if stdout is None:
            return
        async for raw in stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                yield line

    async def wait(self) -> int:
        """Wait for the exit code, and for the stderr drain unless a leaked pipe keeps it open."""
        returncode = await self._process.wait()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(self._stderr_task), _STDERR_DRAIN_SECONDS)
        return returncode

    async def terminate(self) -> None:
        """Stop the process group: SIGTERM, then SIGKILL after a grace period. Safe to call repeatedly.

        The stop runs as its own task and is shielded from the caller, so cancelling the caller does not leave
        the process half-stopped.
        """
        if self._process.returncode is not None:
            return
        if self._termination is None:
            self._killed_by_us = True
            self._termination = asyncio.ensure_future(self._terminate())
        await asyncio.shield(self._termination)

    async def close(self) -> None:
        """Stop the process if it is still running and release the stderr drain."""
        try:
            if self._process.returncode is None:
                await self.terminate()
        finally:
            self._stderr_task.cancel()

    async def _terminate(self) -> None:
        pid = self._process.pid
        _signal_group(pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(self._process.wait(), _TERMINATE_GRACE_SECONDS)
            return
        except TimeoutError:
            logger.warning("cli_process_ignored_sigterm pid=%d", pid)
        _signal_group(pid, _KILL)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._process.wait(), _TERMINATE_GRACE_SECONDS)

    async def _drain_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:
            return
        while chunk := await stderr.read(_STDERR_READ_BYTES):
            self._stderr_tail = (self._stderr_tail + chunk)[-_STDERR_TAIL_BYTES:]


@asynccontextmanager
async def spawn_cli_process(
    args: list[str],
    *,
    env: dict[str, str],
    cwd: str,
    stdin_text: str | None,
) -> AsyncIterator[CliProcess]:
    """Spawn ``args`` as its own process group, feed ``stdin_text`` (the prompt) if given, stop it on exit."""
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin_text is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
        limit=_STDOUT_LINE_LIMIT,
        **get_process_group_kwargs(),
    )
    cli_process = CliProcess(process)
    try:
        if stdin_text is not None:
            await cli_process.send_prompt(stdin_text)
        yield cli_process
    finally:
        await cli_process.close()
