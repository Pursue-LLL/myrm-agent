"""Candidate discovery policy and Python-tier discovery for file search tools.

[INPUT]
- core.security.safe_git::hardened_git_argv (POS: git argv that runs no program the repository chose)
- subprocess (POS: git capability probe, git-aware file listing and ignore check)
- os.walk, os.path (POS: bounded traversal fallback; entry checks that answer False where pathlib raises)
- pathspec (POS: gitignore pattern matching for the ignore files of a plain folder, or of a nested repository git cannot list)
- pathlib::Path (POS: path normalization)
- glob_match::glob_matches (POS: shared glob semantics for the ripgrep and Python tiers)

[OUTPUT]
- collect_candidate_files: Consistent fallback candidate list for `glob_tool` and `grep_tool`
- VCS_DIR_NAMES, VCS_EXCLUDE_GLOB: Version-control internals that no listing includes, and the ripgrep ``--glob`` for them
- DEFAULT_PRUNED_DIR_NAMES: Dependency, build and cache directories skipped in plain folders

[POS]
Shared discovery layer for file-search tools. Holds the policy both tiers follow (version-control directories are never
listed; ignore files apply unless the caller opts out; hidden files are searched; symbolic links are never followed; an
entry below the search root that the file system will not describe is skipped, not an error) and implements it for the
Python tier: git-aware listing where available (a repository nested in the checkout is listed by git in turn, and walked
under its ignore files only when git cannot read it; a search root that git itself ignores is walked like a plain
folder), the ignore files of every directory and default directory pruning in non-git directories, bounded traversal.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Collection, Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from myrm_agent_harness.core.security.safe_git import hardened_git_argv

from .glob_match import glob_matches, is_match_all

if TYPE_CHECKING:
    from pathspec import PathSpec
    from pathspec.pattern import Pattern

logger = logging.getLogger(__name__)

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
# Ascending rank: ripgrep lets a .rgignore outrank a .ignore, which outranks a .gitignore.
_IGNORE_FILE_NAMES = (".gitignore", ".ignore", ".rgignore")
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
    # ``dict.fromkeys`` drops the repeats and keeps git's order, which decides the files that fall under ``max_files``
    # and the order of the matches; a set would reorder them from one process to the next.
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

    None means ``repo_dir`` holds no checkout (a submodule that was never initialised is an empty directory, and one
    that cannot be searched shows none), or git refuses its configuration or layout.
    """
    if not os.path.exists(repo_dir / ".git"):
        return None
    try:
        return _git_listing(repo_dir, ".", timeout_seconds)
    except _GIT_FAILURES:
        return None


class _IgnoreLayer(NamedTuple):
    """One ignore file, which applies below the directory that holds it."""

    rank: int  # index into _IGNORE_FILE_NAMES
    prefix: str  # that directory relative to the walk root, with a trailing slash ("" for the root itself)
    spec: PathSpec[Pattern]


def _compile_ignore_file(ignore_file: Path) -> PathSpec[Pattern] | None:
    """Compile ``ignore_file`` the way git and ripgrep read it, or None when it is unusable.

    Lines go to pathspec as written: git keeps leading whitespace and honours an escaped trailing space, so trimming a
    line changes what it matches. A file that is not a regular file, cannot be read or cannot be compiled never fails
    or stalls a search; it just does not filter.
    """
    if not os.path.isfile(ignore_file):
        return None  # reading a FIFO or a device would block for good
    try:
        # Imported on first use: the import costs ~18 ms, which searches that go through git or ripgrep never pay.
        import pathspec
    except ImportError:
        # A build that lacks the dependency keeps searching, unfiltered, rather than failing every directory search.
        return None

    try:
        # utf-8-sig: editors on Windows write a byte order mark, which ripgrep drops and which would otherwise stay
        # glued to the first pattern.
        lines = ignore_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as error:
        logger.warning(f"Cannot read ignore file {ignore_file}: {error}")
        return None
    try:
        return pathspec.PathSpec.from_lines("gitignore", lines)
    except Exception as error:
        # The file is user-authored, and what pathspec raises for a line it cannot compile is not a stable contract (its
        # own pattern error, the regex compiler's, or a warning a host turns into an error), so any failure costs the
        # file, never the search.
        logger.warning(f"Ignoring unusable ignore file {ignore_file}: {error}")
        return None


def _extend_layers(
    layers: tuple[_IgnoreLayer, ...], directory: Path, prefix: str, filenames: Collection[str]
) -> tuple[_IgnoreLayer, ...]:
    """``layers`` plus the ignore files ``directory`` holds, highest priority first.

    ripgrep asks the kinds in order (.rgignore, .ignore, .gitignore) and, within a kind, the deepest file first; the
    first file with an opinion on a path decides, so that is the order the layers are kept in.
    """
    own: list[_IgnoreLayer] = []
    for rank, name in enumerate(_IGNORE_FILE_NAMES):
        if name not in filenames:
            continue
        spec = _compile_ignore_file(directory / name)
        if spec is not None:
            own.append(_IgnoreLayer(rank, prefix, spec))
    if not own:
        return layers
    return tuple(sorted((*layers, *own), key=lambda layer: (layer.rank, len(layer.prefix)), reverse=True))


def _is_ignored(layers: tuple[_IgnoreLayer, ...], rel_path: str, *, is_dir: bool) -> bool:
    """Whether the first layer with an opinion on ``rel_path`` (relative to the walk root) ignores it.

    A directory is asked with a trailing slash, the way git and ripgrep ask: a pattern for directories only (``dir/``)
    must match it, and a negated one takes it back.
    """
    for layer in layers:
        relative = rel_path[len(layer.prefix) :]
        verdict = layer.spec.check_file(f"{relative}/" if is_dir else relative).include
        if verdict is not None:
            return verdict
    return False


def _walk_files(root: Path, *, pruned: frozenset[str], honour_ignore_files: bool) -> Iterator[Path]:
    """Yield the regular files below ``root``, skipping ``pruned`` directory names and what its ignore files cover.

    Version-control markers (the ``.git`` file of a submodule included) and symbolic links are never yielded, and
    neither is an entry the file system will not describe (a directory that can be listed but not searched, a path
    beyond the platform's length limit): the ``os.path`` predicates answer False for it where ``Path`` raises, and one
    such entry must not fail the whole search.
    """
    # The layers a directory inherits from its parent, keyed by its path and dropped when the walk enters it. A
    # symbolic link to a directory is never entered, so its entry lasts until the walk ends.
    inherited: dict[str, tuple[_IgnoreLayer, ...]] = {str(root): ()}
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        layers: tuple[_IgnoreLayer, ...] = ()
        prefix = ""
        if honour_ignore_files:
            prefix = "" if current_dir == root else f"{current_dir.relative_to(root).as_posix()}/"
            layers = _extend_layers(inherited.pop(dirpath), current_dir, prefix, filenames)

        kept_dirs: list[str] = []
        for dirname in dirnames:
            if dirname in pruned or (layers and _is_ignored(layers, f"{prefix}{dirname}", is_dir=True)):
                continue
            kept_dirs.append(dirname)
            if honour_ignore_files:
                inherited[os.path.join(dirpath, dirname)] = layers
        dirnames[:] = kept_dirs

        for filename in filenames:
            if filename in VCS_DIR_NAMES:
                continue
            file_path = current_dir / filename
            if os.path.islink(file_path) or not os.path.isfile(file_path):
                continue
            if layers and _is_ignored(layers, f"{prefix}{filename}", is_dir=False):
                continue
            yield file_path


def _expand_git_entries(entries: Iterable[Path]) -> Iterator[Path]:
    """Yield the files behind the entries git listed.

    A directory entry is a repository or submodule nested in the checkout, and git lists it in turn under the
    ignore files of its own tree, as ripgrep reads them. Only when git cannot list it is it walked under its ignore
    files: dependency and build directories are not skipped there, since inside a git checkout the ignore rules
    decide. An entry the file system will not describe is skipped, as in ``_walk_files``.
    """
    pending = [iter(entries)]
    while pending:
        entry = next(pending[-1], None)
        if entry is None:
            pending.pop()
            continue
        if os.path.islink(entry):
            continue
        if os.path.isfile(entry):
            yield entry
        elif os.path.isdir(entry):
            nested = _list_nested_repository(entry)
            if nested is None:
                yield from _walk_files(entry, pruned=VCS_DIR_NAMES, honour_ignore_files=True)
            else:
                pending.append(iter(nested))


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
            files = _walk_files(search_root, pruned=VCS_DIR_NAMES, honour_ignore_files=False)
        else:
            files = _walk_files(search_root, pruned=DEFAULT_PRUNED_DIR_NAMES, honour_ignore_files=True)

    candidates: list[Path] = []
    for file_path in files:
        if not _pattern_matches(file_path, search_root, file_pattern):
            continue
        candidates.append(file_path)
        if len(candidates) >= max_files:
            break
    return candidates
