"""Text reads that cannot exhaust memory or block on a file that is not a plain file.

Whoever can write a folder chooses what sits under the names the product reads in it: a file of many gigabytes, a
symlink to an endless device, or a FIFO that never delivers a byte. ``Path.read_text`` waits for all of them, so a read
of an untrusted file goes through here instead: the kind of the file is decided on the descriptor that is then read
(no second look at the path), and at most ``max_chars + 1`` characters are ever decoded.

[INPUT]
- core.security.path.filesystem::is_within_boundary (POS: symlink-safe containment check, used when a boundary is given)
- (stdlib: os, stat, dataclasses, enum, pathlib)

[OUTPUT]
- ReadRefusal: why a read was refused (outside the boundary, not a regular file, over the limit)
- BoundedRead: the text, or the refusal, and how many characters were read
- read_text_bounded(path, max_chars, *, boundary, errors) -> BoundedRead — bounded replacement for ``Path.read_text``

[POS]
Read primitive of the path-safety package for files whose content the product does not control (workspace rules, skills,
repo config). It decides nothing about what a refusal means to the caller; I/O errors (missing file, permission) are not
caught and surface as ``OSError`` exactly as with ``Path.read_text``.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from myrm_agent_harness.core.security.path.filesystem import is_within_boundary

__all__ = ("BoundedRead", "ReadRefusal", "read_text_bounded")

# O_NONBLOCK keeps the open of a FIFO from waiting for a writer (the kind is checked right after); O_BINARY stops the
# Windows C runtime from translating line endings, which the text layer below does itself, as ``Path.read_text`` does.
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


class ReadRefusal(StrEnum):
    """Why :func:`read_text_bounded` returned no text."""

    OUTSIDE_BOUNDARY = "outside_boundary"
    NOT_A_REGULAR_FILE = "not_a_regular_file"
    TOO_LARGE = "too_large"


@dataclass(frozen=True, slots=True)
class BoundedRead:
    """The outcome of one bounded read: ``text`` when read in full, else the ``refusal``.

    ``chars_read`` is what was decoded (``max_chars + 1`` for a file over the limit, 0 for a file never opened), so a
    caller that keeps a budget can charge exactly what the read cost.
    """

    text: str | None
    refusal: ReadRefusal | None
    chars_read: int


def _open_regular(path: str | Path) -> int | None:
    """A read-only descriptor for *path*, or None (descriptor closed again) when it is not a regular file."""
    fd = os.open(path, _OPEN_FLAGS)
    try:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            return fd
    except BaseException:
        os.close(fd)
        raise
    os.close(fd)
    return None


def read_text_bounded(
    path: str | Path,
    max_chars: int,
    *,
    boundary: str | Path | None = None,
    errors: Literal["strict", "replace"] = "strict",
) -> BoundedRead:
    """Read the UTF-8 text of a regular file, taking at most *max_chars* characters.

    With a *boundary*, a path that resolves outside it is refused before it is opened. A file that is not a regular
    file (FIFO, device, directory) is refused without a read. A longer file is refused as ``TOO_LARGE`` after
    ``max_chars + 1`` characters, never read to its end. *errors* is the decoder policy of ``Path.read_text``.
    """
    if boundary is not None and not is_within_boundary(path, boundary):
        return BoundedRead(None, ReadRefusal.OUTSIDE_BOUNDARY, 0)
    fd = _open_regular(path)
    if fd is None:
        return BoundedRead(None, ReadRefusal.NOT_A_REGULAR_FILE, 0)
    with os.fdopen(fd, encoding="utf-8", errors=errors) as handle:
        text = handle.read(max_chars + 1)
    if len(text) > max_chars:
        return BoundedRead(None, ReadRefusal.TOO_LARGE, len(text))
    return BoundedRead(text, None, len(text))
