"""Atomic file write with crash-consistency guarantee.

Writes content to a file via tmpfile + fsync + atomic rename, ensuring:
- No partial/truncated files on process crash
- No data loss on power failure (fsync flushes to disk)
- No name collision under concurrent processes (mkstemp)
- Text lands byte-for-byte as UTF-8: no newline translation on any platform

Usage::

    from myrm_agent_harness.infra.atomic_write import atomic_write, async_atomic_write

    atomic_write(path, json.dumps(data))                     # sync
    await async_atomic_write(path, json.dumps(data))         # async
    atomic_write(path, binary_content, mode=None)             # no chmod

[INPUT]
- (none)

[OUTPUT]
- atomic_write: Atomically write content to a file.
- async_atomic_write: Async wrapper around :func:`atomic_write` via ``asyncio.to_thread``.

[POS]
Atomic file write with crash-consistency guarantee.
"""

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write(
    path: str | Path,
    content: str | bytes,
    *,
    mode: int | None = 0o600,
) -> None:
    """Atomically write content to a file.

    Args:
        path: Target file path.
        content: Text (str) or binary (bytes) content to write. Text is encoded as UTF-8 and stored verbatim, so
            the file holds exactly ``content.encode("utf-8")`` on every platform.
        mode: File permission bits (default 0o600). Pass None to skip chmod.
    """
    # Bytes in every case: a text-mode file writes "\n" as "\r\n" on Windows, so the file would no longer hold the
    # bytes the caller hashed, measured or counted lines of.
    data = content.encode("utf-8") if isinstance(content, str) else content
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd = -1
    tmp_path: str | None = None

    try:
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, prefix=".atomic_")

        with os.fdopen(fd, "wb") as f:
            fd = -1  # fdopen takes ownership
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        if mode is not None:
            os.chmod(tmp_path, mode)

        try:
            os.replace(tmp_path, target)
        except OSError as e:
            import errno

            if e.errno == errno.EXDEV:
                import shutil

                shutil.move(tmp_path, target)
            else:
                raise
        tmp_path = None  # replaced successfully, no cleanup needed

        # fsync parent directory to ensure rename is durable on ext4/XFS
        try:
            dir_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass  # Windows/special FS reject directory fds — safe to ignore

    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


async def async_atomic_write(
    path: str | Path,
    content: str | bytes,
    *,
    mode: int | None = 0o600,
) -> None:
    """Async wrapper around :func:`atomic_write` via ``asyncio.to_thread``."""
    await asyncio.to_thread(atomic_write, path, content, mode=mode)
