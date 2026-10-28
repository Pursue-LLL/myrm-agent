"""Helpers for tests that run a real ``git`` against repositories whose config names marker-writing programs.

[INPUT]
- git (POS: the real binary under test, never mocked)

[OUTPUT]
- git / run / plain: run git, or build a plain (un-hardened) argv for the control run
- program / fired / clear: marker-writing scripts and a record of which of them ran

[POS]
Shared by ``test_safe_git*.py``: a program that ran leaves a marker file, so "the hardened command ran nothing" is an
observation and not an inference.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def program(markers: Path, name: str, *, passthrough: str = "") -> str:
    """A script that records that it ran, then passes its input through (``cat`` or ``cat "$1"``)."""
    script = markers.parent / f"{name}.sh"
    script.write_text(f"#!/bin/sh\ntouch '{markers}/{name}'\n{passthrough}\n")
    script.chmod(0o755)
    return str(script)


def fired(markers: Path) -> set[str]:
    return {entry.name for entry in markers.iterdir()}


def clear(markers: Path) -> None:
    for entry in markers.iterdir():
        entry.unlink()


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, check=False)


def plain(repo: Path, *args: str) -> list[str]:
    return ["git", "-C", str(repo), *args]
