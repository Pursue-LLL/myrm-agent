"""Optional POSIX PTY spawn for background bash jobs (PIPE fallback elsewhere).

[INPUT]
- executors.models::AsyncProcessProtocol (POS: subprocess handle protocol)
- utils.os_compat::kill_process_group, kill_spawned_group, SIGKILL (POS: cross-platform process-group control)

[OUTPUT]
- try_spawn_background_pty: Spawn with merged stdout/stderr on a PTY master fd

[POS]
POSIX PTY spawn adapter for interactive CLIs (npm create, python input()); skipped when an OS sandbox wraps the
command or on non-POSIX hosts, where callers fall back to PIPE. A job that exits at once keeps its output (the Linux
EIO hang-up reads as a clean end of stream; the slave descriptor is released on a thread of its own once the reader is
attached), and a spawn that fails or is cancelled once the child runs stops the child's process group.
"""

from __future__ import annotations

import asyncio
import errno
import logging
import os
import signal
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from myrm_agent_harness.toolkits.code_execution.executors.models import (
    AsyncProcessProtocol,
)
from myrm_agent_harness.utils import os_compat

logger = logging.getLogger(__name__)

_STREAM_LIMIT_BYTES = 8 * 1024 * 1024


class _PtyStdinWriter:
    """Write-only stdin shim over a PTY master fd."""

    def __init__(self, master_fd: int) -> None:
        self._fd = master_fd
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            raise BrokenPipeError("PTY stdin is closed")
        os.write(self._fd, data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with suppress(OSError):
            os.write(self._fd, b"\x04")

    async def wait_closed(self) -> None:
        return None


class _PtyProcessWrapper(AsyncProcessProtocol):
    """AsyncProcessProtocol backed by a subprocess attached to a PTY slave."""

    def __init__(
        self,
        proc: asyncio.subprocess.Process,
        *,
        master_fd: int,
        stdout_reader: asyncio.StreamReader,
        read_transport: asyncio.BaseTransport,
        read_file: object,
    ) -> None:
        self._proc = proc
        self._master_fd = master_fd
        self._stdout_reader = stdout_reader
        self._read_transport = read_transport
        self._read_file = read_file
        self._stdin_writer = _PtyStdinWriter(master_fd)

    @property
    def stdin(self) -> _PtyStdinWriter:
        return self._stdin_writer

    @property
    def stdout(self) -> asyncio.StreamReader:
        return self._stdout_reader

    @property
    def stderr(self) -> None:
        return None

    async def wait(self) -> int:
        return await self._proc.wait()

    def terminate(self) -> None:
        os_compat.kill_process_group(self._proc.pid, signal.SIGTERM)

    def kill(self) -> None:
        os_compat.kill_process_group(self._proc.pid, os_compat.SIGKILL)


def pty_spawn_eligible(*, sandbox_enabled: bool) -> bool:
    """PTY is only attempted on POSIX hosts without OS-level sandbox wrapping."""
    return os.name != "nt" and not sandbox_enabled


class _PtyReaderProtocol(asyncio.StreamReaderProtocol):
    """Stream protocol that reads the PTY hang-up as a clean end of stream.

    Once the slave side is closed, Linux fails the next master read with EIO (macOS returns EOF).
    asyncio then calls ``StreamReader.set_exception``, which makes every later ``readline`` raise and
    drops the lines still buffered, so the tail of a short-lived job's output would be lost.
    """

    def connection_lost(self, exc: Exception | None) -> None:
        if isinstance(exc, OSError) and exc.errno == errno.EIO:
            exc = None
        super().connection_lost(exc)


async def _connect_pty_reader(master_fd: int) -> tuple[asyncio.StreamReader, asyncio.BaseTransport, object]:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=_STREAM_LIMIT_BYTES)
    protocol = _PtyReaderProtocol(reader)
    read_file = os.fdopen(master_fd, "rb", buffering=0)
    try:
        transport, _ = await loop.connect_read_pipe(lambda: protocol, read_file)
    except BaseException:
        read_file.close()
        raise
    return reader, transport, read_file


def _close_quietly(fd: int) -> None:
    with suppress(OSError):
        os.close(fd)


async def try_spawn_background_pty(
    *,
    full_cmd_array: list[str],
    effective_cwd: Path | None,
    env: dict[str, str],
    preexec_fn: Callable[[], None] | None,
    process_group_kwargs: dict[str, Any],  # os_compat's platform-specific Popen kwargs; unpacked into asyncio below
) -> AsyncProcessProtocol | None:
    """Spawn via PTY; returns None when the platform cannot create a PTY pair."""
    import pty  # POSIX-only: a module-level import would make this module unimportable on Windows

    try:
        master_fd, slave_fd = pty.openpty()
    except OSError as exc:
        logger.debug("PTY openpty unavailable: %s", exc)
        return None

    master_open = slave_open = True
    try:
        kwargs = dict(process_group_kwargs)
        kwargs.setdefault("limit", _STREAM_LIMIT_BYTES)
        if os.name != "nt" and preexec_fn is not None:
            kwargs["preexec_fn"] = preexec_fn

        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd_array,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(effective_cwd) if effective_cwd else None,
                env=env,
                **kwargs,
            )
        except OSError as exc:
            logger.warning("PTY subprocess spawn failed: %s", exc)
            return None

        # The file object that the reader wraps around the master owns that descriptor from here on.
        master_open = False
        try:
            stdout_reader, read_transport, read_file = await _connect_pty_reader(master_fd)
            # A child that has already finished leaves this process holding the last descriptor of the slave. Closing it
            # then waits until the master's reader has taken what the child wrote, and macOS discards that output when
            # the wait runs out. The reader runs on this loop, so the close must not block it. A thread of its own does
            # the close, not the shared default executor: a spawn must never wait for a worker that a busy executor
            # holds.
            threading.Thread(target=_close_quietly, args=(slave_fd,), name="pty-slave-close", daemon=True).start()
            slave_open = False
        except BaseException:
            # The job runs and no wrapper owns it yet, so nothing would ever stop it. The hang-up of the master that
            # closes with the reader does not reach a job that ignores SIGHUP, as one started with ``nohup`` does.
            os_compat.kill_spawned_group(proc.pid)
            raise
    finally:
        if master_open:
            _close_quietly(master_fd)
        if slave_open:
            _close_quietly(slave_fd)

    logger.info(" [LocalExecutor] Background PTY spawn pid=%s", proc.pid)
    return _PtyProcessWrapper(
        proc,
        master_fd=master_fd,
        stdout_reader=stdout_reader,
        read_transport=read_transport,
        read_file=read_file,
    )


__all__ = ["pty_spawn_eligible", "try_spawn_background_pty"]
