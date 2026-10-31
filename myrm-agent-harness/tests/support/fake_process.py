"""A subprocess double whose pipes are real streams, for tests that must not start a program.

[INPUT]
- asyncio::StreamReader (POS: the pipe type ``Process.stdout`` / ``Process.stderr`` really are)

[OUTPUT]
- FakeProcess: a finished child that has already written the given stdout and stderr and exited with the given code

[POS]
Shared by the tests that patch ``asyncio.create_subprocess_exec`` to hand the code under test a child. The code reads
the pipes as it would from a real child (``communicate_bounded`` reads ``proc.stdout`` and ``proc.stderr`` until they end),
so a ``MagicMock`` process with only ``communicate`` mocked is not enough: its pipes are never-ending mocks.
"""

from __future__ import annotations

import asyncio


def _ended(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class FakeProcess:
    """A finished child: both pipes hold what it wrote and then end, and ``wait`` reports its exit code."""

    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, pid: int = 4242) -> None:
        self.stdout = _ended(stdout)
        self.stderr = _ended(stderr)
        self.stdin: asyncio.StreamWriter | None = None
        self.pid = pid
        self.returncode: int | None = returncode

    async def wait(self) -> int:
        return self.returncode or 0

    def kill(self) -> None:
        """Nothing to stop: the child has already exited."""

    def terminate(self) -> None:
        """Nothing to stop: the child has already exited."""
