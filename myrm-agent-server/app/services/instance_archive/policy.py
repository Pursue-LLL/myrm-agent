"""Instance archive path classification policy.

[INPUT]
- pathlib / os: state-dir traversal without following symlinks

[OUTPUT]
- PathCategory / PathDecision: why a path is carried or left behind
- classify_path: decision for a state-dir-relative path
- scan_state_dir: StateScan (carried files, excluded paths, and carried paths that could not be read) for export
- is_importable_entry / top_level_name: import-side allow-check (hostile archives cannot overwrite excluded paths)
- is_standard_layout: whether the main database sits where the archive expects it

[POS]
Business policy of "what an instance backup carries". Include-by-default so a
newly added data store is never silently lost; secrets, host identity,
rebuildable indexes and in-flight runtime files are excluded explicitly.
The same classifier gates export, staging extraction and promotion planning.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from myrm_agent_harness.infra.state_archive import is_sqlite_file

MAIN_DB_NAME = "data.db"
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_TRANSIENT_SUFFIXES = (".lock", ".pyc", ".tmp", ".partial")
# Runtime stores recognised by file name because their directory is chosen by the deployment (a `data/` folder in
# the state directory, or the state directory itself). The subagent checkpoint store holds the conversation of
# every subagent run, keyed by task and not by chat, so no per-chat rule can scrub it; its threads cannot resume
# after a restart, so a restored copy would be dead weight anyway.
_RUNTIME_FILE_NAMES = frozenset({"subagent_checkpoints.sqlite"})


class PathCategory(StrEnum):
    DATA = "data"
    SECRET = "secret"  # logins and credentials: never travel, the user signs in again
    MACHINE_KEY = "machine_key"  # key material of this host: never travels, the target keeps or generates its own
    HOST_BOUND = "host_bound"  # security posture / machine identity of the target host
    DERIVED = "derived"  # rebuildable from carried data
    RUNTIME = "runtime"  # locks, caches, in-flight journals, toolchains
    LOCAL_HISTORY = "local_history"  # backups, snapshots, logs of this host


@dataclass(frozen=True, slots=True)
class PathDecision:
    category: PathCategory

    @property
    def include(self) -> bool:
        return self.category is PathCategory.DATA


_DATA = PathDecision(PathCategory.DATA)

# Top-level state-dir names that never travel. Each rule covers the whole subtree.
_EXCLUDED_TOP_LEVEL: dict[str, PathCategory] = {
    # This machine's key material: regenerated on the target, nothing for the user to do
    ".encryption_key": PathCategory.MACHINE_KEY,
    "vault.key": PathCategory.MACHINE_KEY,
    # Logins and sessions encrypted under those keys: the user signs in again
    "session_vault": PathCategory.SECRET,
    "whatsapp_auth": PathCategory.SECRET,
    "matrix": PathCategory.SECRET,
    # Host-bound access control (password hashes, pairing state)
    "webui": PathCategory.HOST_BOUND,
    # Rebuildable indexes / derived state. The embedded vector store (`qdrant/`) is deliberately
    # absent: it holds the semantic and episodic memory content itself, so it travels as data.
    "skill_scans": PathCategory.DERIVED,
    "config_hash": PathCategory.DERIVED,
    "config_snapshot.json": PathCategory.DERIVED,
    "config_version": PathCategory.DERIVED,
    # Runtime: locks, caches, toolchains, in-flight journals
    "instance_archive": PathCategory.RUNTIME,
    "locks": PathCategory.RUNTIME,
    "venvs": PathCategory.RUNTIME,
    "toolchains": PathCategory.RUNTIME,
    "cache": PathCategory.RUNTIME,
    "spillover": PathCategory.RUNTIME,
    "tee": PathCategory.RUNTIME,
    "quarantine": PathCategory.RUNTIME,
    "dlq": PathCategory.RUNTIME,
    "inbound_journal.db": PathCategory.RUNTIME,
    "delivery_notify_ledger.db": PathCategory.RUNTIME,
    # Backups / logs of this host
    "snapshots": PathCategory.LOCAL_HISTORY,
    "sqlite_backups": PathCategory.LOCAL_HISTORY,
    "backups": PathCategory.LOCAL_HISTORY,
    "logs": PathCategory.LOCAL_HISTORY,
    "mcp_logs": PathCategory.LOCAL_HISTORY,
    "data.db.optimize_backup": PathCategory.LOCAL_HISTORY,
}

# Regenerable directories inside any carried tree.
_REGENERABLE_DIRS = frozenset({"node_modules", ".venv", "venv", "__pycache__", ".cache"})

# Trees whose contents are user-authored: file names inside are never second-guessed.
_USER_CONTENT_TREES = frozenset(
    {
        ("wiki",),
        ("skills",),
        ("workspace_deliverables",),
        ("harness", "workspace"),
        ("harness", ".memories"),
    }
)

# Unknown names at the state-dir (or harness/) top level that look like key material stay home.
_SECRET_NAME_RE = re.compile(r"secret|token|credential|passw(or)?d|private|\.key$|\.pem$", re.IGNORECASE)


def classify_path(parts: tuple[str, ...]) -> PathDecision:
    """Decide whether the state-dir-relative path ``parts`` is carried."""
    name = parts[-1]
    if name.endswith(_SQLITE_SIDECAR_SUFFIXES) or name in _RUNTIME_FILE_NAMES:
        return PathDecision(PathCategory.RUNTIME)
    top = _EXCLUDED_TOP_LEVEL.get(parts[0])
    if top is not None:
        return PathDecision(top)
    if any(part in _REGENERABLE_DIRS for part in parts):
        return PathDecision(PathCategory.DERIVED)
    if name == "credentials.json" and len(parts) >= 2 and parts[-2] == ".myrm":
        return PathDecision(PathCategory.SECRET)
    if name.endswith(_TRANSIENT_SUFFIXES):
        return PathDecision(PathCategory.RUNTIME)
    at_top_level = len(parts) == 1 or (len(parts) == 2 and parts[0] == "harness")
    if at_top_level and parts not in _USER_CONTENT_TREES and _SECRET_NAME_RE.search(name):
        return PathDecision(PathCategory.SECRET)
    return _DATA


def top_level_name(rel_path: str) -> str:
    return rel_path.split("/", 1)[0]


def is_standard_layout(state_dir: Path, sqlite_path: Path) -> bool:
    """The archive only understands an instance whose main database lives directly in the state directory."""
    return sqlite_path == state_dir / MAIN_DB_NAME


def is_importable_entry(rel_path: str) -> bool:
    """Import-side gate: an archive entry may only land where an export could have put it."""
    parts = tuple(p for p in rel_path.split("/") if p)
    return bool(parts) and ".." not in parts and "." not in parts and classify_path(parts).include


@dataclass(frozen=True, slots=True)
class SourceFile:
    rel: str
    path: Path
    size: int
    is_sqlite: bool


@dataclass(frozen=True, slots=True)
class ExcludedPath:
    rel: str
    category: PathCategory


@dataclass(frozen=True, slots=True)
class UnreadablePath:
    """A path that is carried by policy but could not be listed or inspected, so it is missing from the scan."""

    rel: str


@dataclass(frozen=True, slots=True)
class StateScan:
    sources: list[SourceFile]
    excluded: list[ExcludedPath]
    unreadable: list[str]


def _walk(root: Path, parts: tuple[str, ...]) -> Iterator[SourceFile | ExcludedPath | UnreadablePath]:
    directory = root.joinpath(*parts)
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except (FileNotFoundError, NotADirectoryError):  # removed while the scan ran (live instance)
        return
    except OSError:
        yield UnreadablePath("/".join(parts) or ".")
        return
    for entry in entries:
        child = (*parts, entry.name)
        rel = "/".join(child)
        decision = classify_path(child)
        if not decision.include:
            yield ExcludedPath(rel, decision.category)
            continue
        if entry.is_symlink():
            yield ExcludedPath(rel, PathCategory.RUNTIME)
        elif entry.is_dir(follow_symlinks=False):
            yield from _walk(root, child)
        elif entry.is_file(follow_symlinks=False):
            path = Path(entry.path)
            try:
                size = entry.stat().st_size
            except FileNotFoundError:  # removed between listing and stat (live instance)
                continue
            except OSError:
                yield UnreadablePath(rel)
                continue
            yield SourceFile(rel, path, size, is_sqlite_file(path))


def scan_state_dir(state_dir: Path) -> StateScan:
    """Walk ``state_dir`` once; sidecar files are folded into their database snapshot."""
    sources: list[SourceFile] = []
    excluded: list[ExcludedPath] = []
    unreadable: list[str] = []
    for item in _walk(state_dir, ()):
        if isinstance(item, SourceFile):
            sources.append(item)
        elif isinstance(item, UnreadablePath):
            unreadable.append(item.rel)
        elif not item.rel.endswith(_SQLITE_SIDECAR_SUFFIXES):
            excluded.append(item)
    return StateScan(sources, excluded, unreadable)
