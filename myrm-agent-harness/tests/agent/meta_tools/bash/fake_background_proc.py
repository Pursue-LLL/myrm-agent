"""Stand-ins for a background job's process handle and its output pipes.

The reader of ``consume_background_entry`` takes each pipe in blocks with ``read(n)``, as asyncio's ``StreamReader``
serves it, so a pipe here delivers the chunks a test queued and ends (or waits for more) the way a real pipe does.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from unittest.mock import MagicMock


class FakeOutputPipe:
    """One output pipe: each queued chunk is served by one ``read`` (cut at ``n`` bytes when larger).

    With the queue empty, the pipe reports end of stream, or, when ``hold_open`` is set, makes the reader wait
    until ``feed`` adds a chunk or ``close`` ends it: the pipe of a program that is still alive.
    """

    def __init__(self, chunks: list[bytes] | None = None, *, hold_open: bool = False) -> None:
        self._chunks: deque[bytes] = deque(chunks or [])
        self._open = hold_open
        self._wakeup = asyncio.Event()

    @property
    def backlog(self) -> int:
        """Chunks queued and not yet read."""
        return len(self._chunks)

    def feed(self, data: bytes) -> None:
        self._chunks.append(data)
        self._wakeup.set()

    def close(self) -> None:
        self._open = False
        self._wakeup.set()

    async def read(self, n: int = -1) -> bytes:
        while not self._chunks:
            if not self._open:
                return b""
            self._wakeup.clear()
            await self._wakeup.wait()
        chunk = self._chunks.popleft()
        if 0 <= n < len(chunk):
            self._chunks.appendleft(chunk[n:])
            chunk = chunk[:n]
        return chunk


class FakeProc:
    """A process handle whose life a test drives: ``wait`` returns once ``finish`` is called.

    The registry stops a job through ``os_compat.kill_spawned_group``, not through this handle, so a test that
    checks kill semantics patches that function and calls ``finish`` from its replacement.
    """

    def __init__(
        self,
        pid: int,
        stdout: list[bytes],
        stderr: list[bytes] | None = None,
        *,
        stdout_pipe: object | None = None,
        stderr_pipe: object | None = None,
        stdin: object | None = None,
    ) -> None:
        self._proc = MagicMock()
        self._proc.pid = pid
        # A job counts as able to wait for input only when it has a stdin to write to.
        self.stdin = stdin
        self.stdout = stdout_pipe if stdout_pipe is not None else FakeOutputPipe(stdout)
        self.stderr = stderr_pipe if stderr_pipe is not None else FakeOutputPipe(stderr)
        self._exit_event = asyncio.Event()
        self._exit_code = 0

    @property
    def pid(self) -> int:
        pid = self._proc.pid
        assert isinstance(pid, int)
        return pid

    async def wait(self) -> int:
        await self._exit_event.wait()
        return self._exit_code

    def terminate(self) -> None:
        self.finish(-15)

    def kill(self) -> None:
        self.finish(-9)

    def finish(self, exit_code: int = 0) -> None:
        """The process exits: its pipes end, as they do when the last holder of the write end is gone."""
        self._exit_code = exit_code
        for pipe in (self.stdout, self.stderr):
            if isinstance(pipe, FakeOutputPipe):
                pipe.close()
        self._exit_event.set()


async def wait_until(predicate: Callable[[], bool], *, timeout_seconds: float = 2.0, what: str = "condition") -> None:
    """Poll until ``predicate`` holds, replacing blind ``asyncio.sleep`` waits.

    Reader tasks flip registry state asynchronously; a fixed sleep is flaky under high load, polling is not.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {what}")
