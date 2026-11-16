"""Which sources make a running Dev Gate coordinator stale.

The coordinator is a daemon that imports its code once. A fingerprint of the content of the sources it executes is
stamped when it starts; a later mismatch means it runs code that is no longer on disk, and the next caller restarts it
when no live session pins the generation. Only each source's bytes and its path below the dev lib root enter the
fingerprint, so identical code in another checkout, or a file rewritten with the same content, does not make a running
coordinator stale.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

# Paths relative to the dev lib root. A directory stands for every module below it, sub-packages included, so a module
# added to the package is covered without editing this list.
COORDINATOR_CODE_SOURCES: tuple[str, ...] = (
    "dev_gate/coordinator.py",
    "dev_gate/cli.py",
    "dev_gate/contract",
    "dev_gate/cleanup_observed_seal.py",
    "dev_gate/owner_identity.py",
    "dev_gate/session.py",
    "dev_gate/private_resource_controller.py",
    "dev_gate/private_admission.py",
    "dev_gate/store",
    "e2e_core/stale_lease_reap.py",
    "e2e_core/pytest_dedupe.py",
    "e2e_session_runtime/registry.py",
    "e2e_core/stack_mutation_policy.py",
)


def _content_digest(path: str | Path) -> str:
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def _modules_below(root: Path) -> list[tuple[str, str]]:
    """Every `*.py` below `root` as (path relative to `root`, content digest), sorted by path.

    A hand-written `os.scandir` walk: `Path.rglob` costs several times as much for the same listing, and a client runs
    this each time it checks a live coordinator for drift. Bytecode caches hold no sources and are not entered.
    """
    found: list[tuple[str, str]] = []
    pending: list[tuple[Path, str]] = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name != "__pycache__":
                        pending.append((Path(entry.path), f"{prefix}{entry.name}/"))
                elif entry.name.endswith(".py"):
                    found.append((f"{prefix}{entry.name}", _content_digest(entry.path)))
    return sorted(found)


def source_fingerprint(lib_root: Path, sources: Iterable[str]) -> str:
    """`name:sha256` of every existing source, joined by `|`; a package entry lists each module below it."""
    parts: list[str] = []
    for name in sources:
        path = lib_root / name
        if path.is_dir():
            parts.extend(f"{name}/{relative}:{digest}" for relative, digest in _modules_below(path))
        elif path.is_file():
            parts.append(f"{name}:{_content_digest(path)}")
    return "|".join(parts)


def coordinator_code_fingerprint() -> str:
    # The dev lib root is the parent of the dev_gate package this module lives in.
    return source_fingerprint(Path(__file__).resolve().parent.parent, COORDINATOR_CODE_SOURCES)
