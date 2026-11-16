"""Spellings of network-share and NT-namespace paths, and a spy that catches any filesystem call made on them.

[INPUT]
- os / os.path / pathlib.Path (POS: the stat, resolve, listing and open calls a path passes through, wrapped)

[OUTPUT]
- HOST: the host every spelling names, on the reserved ``.test`` top-level domain so a lookup cannot reach a real machine
- REFUSED_ON_EVERY_HOST: Windows-syntax spellings (UNC share, extended-length and device namespaces, NT object namespace)
- REFUSED_ON_WINDOWS_ONLY: forward-slash and mixed spellings, a UNC only where the host is Windows
- ORDINARY_PATHS: spellings no host may refuse as a network path
- forbid_touching: record and refuse every filesystem call whose arguments contain a marker; the record stays empty
  when a path was refused on its text

[POS]
Shared by the tests of every gate that refuses a network or NT-namespace path (the path predicate, the file validators,
the executor, the file read tool, the approval path policy). On Windows, opening such a path connects to the host it
names and sends the user's credentials, so each gate has to decide on the text; the spy turns "the filesystem was
reached first" into a failing assertion even where the gate would swallow the exception.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

HOST = "evil.test"

REFUSED_ON_EVERY_HOST: dict[str, str] = {
    "unc": rf"\\{HOST}\share\a.txt",
    "unc-webdav": rf"\\{HOST}@SSL\share\a.txt",
    "unc-admin-share": r"\\localhost\C$\x.txt",
    "unc-surrounding-whitespace": rf"  \\{HOST}\share",
    "extended-length-drive": r"\\?\C:\x.txt",
    "extended-length-unc": rf"\\?\UNC\{HOST}\share\a.txt",
    "device-namespace": r"\\.\pipe\x",
    "nt-object-drive": r"\??\C:\x.txt",
    "nt-object-unc": rf"\??\UNC\{HOST}\share\a.txt",
}

# Two or more leading slashes are an ordinary absolute path on POSIX (`//tmp` exists on macOS).
REFUSED_ON_WINDOWS_ONLY: dict[str, str] = {
    "forward-slash-unc": f"//{HOST}/share/a.txt",
    "forward-slash-double-root": "//tmp/x.txt",
    "forward-slash-triple-root": f"///{HOST}/share/a.txt",
    "mixed-separators": rf"/\{HOST}\share\a.txt",
    "mixed-separators-reversed": rf"\/{HOST}/share/a.txt",
    "mixed-three-separators": rf"//\{HOST}\share\a.txt",
}

ORDINARY_PATHS: tuple[str, ...] = (
    r"C:\Users\me\a.txt",
    "C:/Users/me/a.txt",
    "/home/me/a.txt",
    r"a\b\c.txt",
    r"\rooted\on\the\current\drive.txt",
    "src/app.py",
    "./a.txt",
    "../a.txt",
    "file with spaces.txt",
    ".gitignore",
    "",
    "   ",
)

_WATCHED_OS = ("stat", "lstat", "listdir", "scandir", "readlink", "open")
_WATCHED_OS_PATH = ("realpath", "exists", "lexists", "isfile", "isdir", "islink")
_WATCHED_PATH = ("resolve", "exists", "stat", "lstat", "is_file", "is_dir", "is_symlink", "iterdir", "open")


def forbid_touching(monkeypatch: pytest.MonkeyPatch, marker: str = HOST) -> list[str]:
    """Record and refuse every filesystem call, from now on, whose arguments contain ``marker``.

    The calls are refused with an ``AssertionError`` and also recorded, so a gate that catches broad exceptions
    still leaves a trace; a test that expects a refusal on the text ends with ``assert touches == []``.
    """
    touches: list[str] = []

    def watch(owner: object, name: str) -> None:
        real = getattr(owner, name)

        def spy(*args: object, **kwargs: object) -> object:
            if any(marker in str(arg) for arg in args):
                touches.append(f"{name}({args[0]})")
                raise AssertionError(f"{name} reached the filesystem with a path that had to be refused: {args[0]}")
            return real(*args, **kwargs)

        monkeypatch.setattr(owner, name, spy)

    for owner, names in ((os, _WATCHED_OS), (os.path, _WATCHED_OS_PATH), (Path, _WATCHED_PATH)):
        for name in names:
            watch(owner, name)
    return touches
