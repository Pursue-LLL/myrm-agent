"""Observe what is opened for reading and how much the bounded text reader asks to read, at the file-system boundary.

[INPUT]
- os.open / os.fdopen (POS: the calls the bounded reader of ``core.security.path.bounded_read`` makes, wrapped)
- pathlib.Path.open (POS: the route of ``Path.read_text``, wrapped too so a read that bypasses the reader still shows up)

[OUTPUT]
- record_opened: names of the files opened for reading by either route, in order
- record_read_sizes: the size argument of every ``read`` the bounded reader makes (``-1`` is a read of the whole file)

[POS]
Shared by the tests that pin "this file was never opened", "this file was opened once" and "this file was never read
whole": the facts are read off the calls that reach the operating system, so a refactor of the reader cannot make them
vacuous, and a second read through another route is counted. Each helper patches through ``monkeypatch`` and is undone
at the end of the test.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import IO

import pytest


class _ReadRecorder:
    """A text file whose ``read`` sizes are appended to a list."""

    def __init__(self, handle: IO[str], sizes: list[int]) -> None:
        self._handle = handle
        self._sizes = sizes

    def __enter__(self) -> _ReadRecorder:
        self._handle.__enter__()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._handle.__exit__(exc_type, exc, tb)

    def read(self, size: int = -1) -> str:
        self._sizes.append(size)
        return self._handle.read(size)


def record_opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The names of the files opened for reading from now on, by the bounded reader or through ``Path.open``."""
    names: list[str] = []
    real_os_open: Callable[..., int] = os.open
    real_path_open: Callable[..., object] = Path.open

    def recording_os_open(path: str | os.PathLike[str], flags: int, *args: int) -> int:
        names.append(Path(path).name)
        return real_os_open(path, flags, *args)

    def recording_path_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        if "r" in mode:
            names.append(self.name)
        return real_path_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", recording_os_open)
    monkeypatch.setattr(Path, "open", recording_path_open)
    return names


def record_read_sizes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The size argument of every ``read`` the reader makes from now on."""
    sizes: list[int] = []
    real_fdopen: Callable[..., IO[str]] = os.fdopen

    def recording(fd: int, *args: object, **kwargs: object) -> _ReadRecorder:
        return _ReadRecorder(real_fdopen(fd, *args, **kwargs), sizes)

    monkeypatch.setattr(os, "fdopen", recording)
    return sizes
