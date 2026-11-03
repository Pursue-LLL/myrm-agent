"""Candidate discovery policy and Python-tier discovery for file search tools.

[INPUT]
- core.security.safe_git::hardened_git_argv (POS: git argv that runs no program the repository chose)
- subprocess (POS: git capability probe, git-aware file listing and ignore check)
- os.walk (POS: bounded filesystem traversal fallback)
- pathspec (POS: gitignore pattern matching for the ignore files at the root of a plain folder or of a nested repository git cannot list)
- pathlib::Path (POS: path normalization)
- glob_match::glob_matches (POS: shared glob semantics for the ripgrep and Python tiers)

[OUTPUT]
- collect_candidate_files: Consistent fallback candidate list for `glob_tool` and `grep_tool`
- VCS_DIR_NAMES, VCS_EXCLUDE_GLOB: Version-control internals that no listing includes, and the ripgrep ``--glob`` for them
- DEFAULT_PRUNED_DIR_NAMES: Dependency, build and cache directories skipped in plain folders

[POS]
Shared discovery layer for file-search tools. Holds the policy both tiers follow (version-control
directories are never listed; ignore files apply unless the caller opts out; hidden files are searched;
symbolic links are never followed) and implements it for the Python tier: git-aware listing where
available (a repository nested in the checkout is listed by git in turn, and walked under the ignore files at its
root only when git cannot read it; a search root that git itself ignores is walked like a plain folder),
root-level ignore files and default directory pruning in non-git directories, bounded traversal.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.safe_git import hardened_git_argv

from .glob_match import glob_matches, is_match_all

if TYPE_CHECKING:
    from pathspec import PathSpec
    from pathspec.pattern import Pattern

# Version-control internals hold no searchable project content, so no listing includes them,
# not even when the caller asks for ignored files.
VCS_DIR_NAMES = frozenset({".git", ".hg", ".svn", ".bzr", ".jj", ".sl"})
VCS_EXCLUDE_GLOB = "!{" + ",".join(sorted(VCS_DIR_NAMES)) + "}"

# Directories skipped while assembling search candidates in a folder that is not a git checkout (inside one,
# git's ignore rules decide). A skip here costs search recall only, so this list may be broader than a
# security sweep's. ``core.security.path.pattern.PRUNED_DIR_NAMES`` is deliberately separate: skipping a
# directory there would leave protected files uncovered.
DEFAULT_PRUNED_DIR_NAMES = VCS_DIR_NAMES | frozenset(
    {
        "node_modules",
        ".next",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".turbo",
        ".cache",
        ".venv",
        "venv",
    }
)
_ROOT_IGNORE_FILE_NAMES = (".gitignore", ".ignore", ".rgignore")
# What a git invocation can fail with: not installed, unreadable, hardened git refusing a repository, too slow.
_GIT_FAILURES = (subprocess.TimeoutExpired, OSError)


def _pattern_matches(path: Path, root: Path, file_pattern: str) -> bool:
    if is_match_all(file_pattern):
        return True
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        rel_path = path
    return glob_matches(rel_path.as_posix(), file_pattern)


def _is_git_ignored(repo_root: Path, pathspec: str, timeout_seconds: float) -> bool:
    """Whether git ignores ``pathspec`` itself (``check-ignore`` exits 0)."""
    check = subprocess.run(
        hardened_git_argv(("check-ignore", "-q", "--", pathspec), repo_dir=repo_root),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return check.returncode == 0


def _git_listing(repo_root: Path, pathspec: str, timeout_seconds: float) -> list[Path] | None:
    """Return what git lists under ``pathspec`` in ``repo_root`` using its index and ignore rules, or None.

    An entry is a file, or a directory for a nested repository or submodule (git names those by their root, not
    by their files), and each is listed once. None means git failed, or ``pathspec`` is itself ignored: git lists
    nothing below an ignored directory, so only the path's own status tells it from an empty one.
    """
    ls_files = subprocess.run(
        hardened_git_argv(
            ("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", pathspec),
            repo_dir=repo_root,
        ),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if ls_files.returncode != 0:
        return None

    # A path that is unmerged (a conflicted merge) has one index entry per stage, so git names it up to three times.
    rel_paths = dict.fromkeys(ls_files.stdout.decode("utf-8", errors="replace").split("\x00"))
    entries = [repo_root / rel_path for rel_path in rel_paths if rel_path]
    if not entries and _is_git_ignored(repo_root, pathspec, timeout_seconds):
        return None
    return entries


def _list_git_entries(search_root: Path, timeout_seconds: float = 5.0) -> list[Path] | None:
    """Return what git lists below ``search_root``, or None when it cannot decide.

    None means git is unavailable, ``search_root`` lies outside a repository, or ``search_root`` is itself ignored.
    """
    try:
        rev_parse = subprocess.run(
            ["git", "-C", str(search_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=min(timeout_seconds, 2.0),
            check=False,
        )
        if rev_parse.returncode != 0:
            return None
        repo_root = Path(rev_parse.stdout.strip())
        if not repo_root.exists():
            return None
        try:
            relative_root = search_root.relative_to(repo_root)
        except ValueError:
            return None
        pathspec = "." if str(relative_root) in {"", "."} else relative_root.as_posix()
        return _git_listing(repo_root, pathspec, timeout_seconds)
    except _GIT_FAILURES:
        return None


def _list_nested_repository(repo_dir: Path, timeout_seconds: float = 5.0) -> list[Path] | None:
    """Return what git lists for the repository checked out in ``repo_dir``, or None when git cannot.

    None means ``repo_dir`` holds no checkout (a submodule that was never initialised is an empty directory), or git
    refuses its configuration or layout.
    """
    if not (repo_dir / ".git").exists():
        return None
    try:
        return _git_listing(repo_dir, ".", timeout_seconds)
    except _GIT_FAILURES:
        return None


def _walk_files(root: Path, *, pruned: frozenset[str], spec: PathSpec[Pattern] | None) -> Iterator[Path]:
    """Yield the regular files below ``root``, skipping ``pruned`` directory names and what ``spec`` ignores.

    Version-control markers (the ``.git`` file of a submodule included) and symbolic links are never yielded.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        kept_dirs: list[str] = []
        for dirname in dirnames:
            if dirname in pruned:
                continue
            if spec is not None:
                rel_dir = (current_dir / dirname).relative_to(root).as_posix()
                if spec.match_file(rel_dir) or spec.match_file(f"{rel_dir}/"):
                    continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            if filename in VCS_DIR_NAMES:
                continue
            file_path = current_dir / filename
            if file_path.is_symlink() or not file_path.is_file():
                continue
            if spec is not None and spec.match_file(file_path.relative_to(root).as_posix()):
                continue
            yield file_path


def _expand_git_entries(entries: Iterable[Path]) -> Iterator[Path]:
    """Yield the files behind the entries git listed.

    A directory entry is a repository or submodule nested in the checkout, and git lists it in turn under the
    ignore files of its own tree, as ripgrep reads them. Only when git cannot list it is it walked under the
    ignore files at its root: dependency and build directories are not skipped there, since inside a git
    checkout the ignore rules decide.
    """
    pending = [iter(entries)]
    while pending:
        entry = next(pending[-1], None)
        if entry is None:
            pending.pop()
            continue
        if entry.is_symlink():
            continue
        if entry.is_file():
            yield entry
        elif entry.is_dir():
            nested = _list_nested_repository(entry)
            if nested is None:
                yield from _walk_files(entry, pruned=VCS_DIR_NAMES, spec=_load_root_ignore_spec(entry))
            else:
                pending.append(iter(nested))


def _load_root_ignore_spec(search_root: Path) -> PathSpec[Pattern] | None:
    """Load root ignore patterns for non-git fallback, or None."""
    try:
        import pathspec
    except ImportError:
        return None

    patterns: list[str] = []
    for filename in _ROOT_IGNORE_FILE_NAMES:
        ignore_file = search_root / filename
        if not ignore_file.is_file():
            continue
        try:
            for raw_line in ignore_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)
        except OSError:
            continue

    if not patterns:
        return None

    try:
        return pathspec.PathSpec.from_lines("gitignore", patterns)
    except Exception:
        return None


def collect_candidate_files(
    *,
    search_root: Path,
    file_pattern: str,
    max_files: int,
    include_ignored: bool,
) -> list[Path]:
    """Collect candidate files for fallback engines with bounded cost."""
    if max_files <= 0:
        return []

    if search_root.is_file():
        # Explicit file targets stay searchable even when hidden or ignored.
        return [search_root] if _pattern_matches(search_root, search_root.parent, file_pattern) else []

    files: Iterable[Path] | None = None
    if not include_ignored:
        entries = _list_git_entries(search_root)
        if entries is not None:
            files = _expand_git_entries(entries)
    if files is None:
        if include_ignored:
            files = _walk_files(search_root, pruned=VCS_DIR_NAMES, spec=None)
        else:
            files = _walk_files(search_root, pruned=DEFAULT_PRUNED_DIR_NAMES, spec=_load_root_ignore_spec(search_root))

    candidates: list[Path] = []
    for file_path in files:
        if not _pattern_matches(file_path, search_root, file_pattern):
            continue
        candidates.append(file_path)
        if len(candidates) >= max_files:
            break
    return candidates
