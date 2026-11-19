"""Make text-mode files translate newlines the way Windows does, on any host.

[INPUT]
- io.open / builtins.open (POS: the call every text-mode open reaches, including ``os.fdopen``, ``Path.open``,
  ``Path.write_text`` and ``open``, wrapped)

[OUTPUT]
- emulate_windows_text_mode: from now on a text-mode open for writing stores ``\\n`` as ``\\r\\n`` unless the caller
  sets ``newline`` itself

[POS]
Lets a test pin "this writer stores text byte-for-byte" on the platform CI runs: the default text mode of Windows turns
``\\n`` into ``\\r\\n`` (a ``\\r\\n`` text into ``\\r\\r\\n``), which no POSIX run shows. The patch goes through
``monkeypatch`` and is undone at the end of the test.
"""

from __future__ import annotations

import builtins
import io
import os
from collections.abc import Callable
from typing import IO

import pytest

_WRITE_MODE_FLAGS = frozenset("wax+")


def emulate_windows_text_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """From now on a text-mode open for writing stores ``\\n`` as ``\\r\\n`` unless the caller passes ``newline``."""
    real_open: Callable[..., IO[str]] = io.open

    def windows_open(
        file: int | str | os.PathLike[str],
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        closefd: bool = True,
        opener: Callable[[str, int], int] | None = None,
    ) -> IO[str]:
        if "b" not in mode and newline is None and _WRITE_MODE_FLAGS & set(mode):
            newline = "\r\n"
        return real_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

    monkeypatch.setattr(io, "open", windows_open)
    monkeypatch.setattr(builtins, "open", windows_open)
