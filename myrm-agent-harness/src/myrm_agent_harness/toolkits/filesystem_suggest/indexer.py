"""
[INPUT]
git CLI (POS: Repository-aware file listing source)
os.walk (POS: Filesystem fallback enumerator)

[OUTPUT]
WorkspacePathIndexer: lists workspace files as root-relative paths with a short TTL cache, and tells whether a listing
reached the enumeration cap and may therefore be incomplete.

[POS]
Local workspace file enumerator. Produces bounded relative file lists for higher-level suggestion and indexing features.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from myrm_agent_harness.core.security.safe_git import hardened_git_argv

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 5.0
_MAX_LISTED_FILES = 50_000
_GIT_TIMEOUT_SECONDS = 2.0
_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".cache",
        ".next",
        ".nuxt",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "__pycache__",
        ".idea",
        ".vscode",
        ".DS_Store",
        ".tox",
        "egg-info",
        ".eggs",
        "node_modules",
        "venv",
        ".venv",
        "env",
        "dist",
        "build",
        "target",
        "out",
    }
)

_cache_lock = threading.Lock()
_file_cache: dict[str, tuple[float, list[str]]] = {}


class WorkspacePathIndexer:
    """List workspace files as paths relative to a root directory."""

    @classmethod
    def list_files(cls, root: str | Path) -> list[str]:
        """Return cached relevant file paths under ``root``; enumeration stops at a fixed maximum (see ``is_truncated``)."""

        root_path = Path(root).expanduser().resolve()
        cache_key = str(root_path)
        now = time.monotonic()
        with _cache_lock:
            cached = _file_cache.get(cache_key)
            if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
                return cached[1]

        files = cls._git_files(root_path)
        if not files:
            files = cls._walk_files(root_path)

        with _cache_lock:
            _file_cache[cache_key] = (now, files)
        return files

    @classmethod
    def clear_cache(cls, root: str | Path | None = None) -> None:
        """Clear cached listings."""

        with _cache_lock:
            if root is None:
                _file_cache.clear()
                return
            _file_cache.pop(str(Path(root).expanduser().resolve()), None)

    @staticmethod
    def is_truncated(files: list[str]) -> bool:
        """True when ``files`` reached the enumeration cap, so the workspace may hold more files than were listed."""

        return len(files) >= _MAX_LISTED_FILES

    @staticmethod
    def _git_files(root: Path) -> list[str]:
        try:
            top_result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                capture_output=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
            if top_result.returncode != 0:
                return []

            repo_top = Path(top_result.stdout.decode("utf-8", "replace").strip()).resolve()
            try:
                subtree = root.relative_to(repo_top).as_posix()
            except ValueError:
                return []
            # Git lists only the workspace subtree: a monorepo subdirectory does not pay for the rest of the repository.
            # ``:(literal)`` keeps a directory name such as ``:docs`` from being read as pathspec magic.
            pathspec = () if subtree == "." else ("--", f":(literal){subtree}")
            list_result = subprocess.run(
                hardened_git_argv(
                    ("ls-files", "-z", "--cached", "--others", "--exclude-standard", *pathspec),
                    repo_dir=repo_top,
                ),
                capture_output=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
            if list_result.returncode != 0:
                return []
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("git file listing failed in %s: %s", root, exc)
            return []

        prefix = "" if subtree == "." else f"{subtree}/"
        files: list[str] = []
        for raw in list_result.stdout.split(b"\0"):
            if not raw:
                continue
            path = raw.decode("utf-8", "replace")
            if not path.startswith(prefix):
                continue
            # A nested repository is listed as ``dir/``; the entry keeps its bare name.
            files.append(path[len(prefix) :].removesuffix("/"))
            if len(files) >= _MAX_LISTED_FILES:
                break
        return files

    @staticmethod
    def _walk_files(root: Path) -> list[str]:
        files: list[str] = []
        try:
            for current_root, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS and not d.startswith(".")]
                current = Path(current_root)
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    try:
                        rel = (current / filename).relative_to(root).as_posix()
                    except ValueError:
                        continue
                    files.append(rel)
                    if len(files) >= _MAX_LISTED_FILES:
                        return files
        except OSError as exc:
            logger.debug("fallback walk failed in %s: %s", root, exc)
        return files
