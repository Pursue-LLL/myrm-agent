"""Locate the git metadata a sandboxed workspace must keep read-only.

A sandbox that makes a workspace writable also makes its ``.git/config`` and ``.git/hooks`` writable, and the
next git call the host makes in that repository then runs whatever the sandboxed command put there
(``core.fsmonitor``, ``core.hooksPath``, hook scripts). The repositories are found when the policy is built:
the workspace itself and its direct child directories, following a ``.git`` pointer file or link to a git
directory that lies inside the workspace (worktrees, submodules).

[INPUT]
- core.security.path::EXECUTABLE_GIT_METADATA, is_within_boundary

[OUTPUT]
- discover_protected_subpaths(work_dir) -> tuple[str, ...]: existing paths that stay read-only inside ``work_dir``

[POS]
Discovery half of the read-only subpath protection; the providers enforce what it returns.
"""

from __future__ import annotations

import logging
import os

from myrm_agent_harness.core.security.path import EXECUTABLE_GIT_METADATA, is_within_boundary

logger = logging.getLogger(__name__)

# Child directories examined for a repository: a workspace holding more is not a collection of checkouts.
_MAX_CHILD_DIRS = 256
_POINTER_READ_BYTES = 4096
_DOT_GIT = ".git"
# Entries inside a git directory, e.g. ("config", "hooks").
_GIT_DIR_ENTRIES = tuple(entry.removeprefix(f"{_DOT_GIT}/") for entry in EXECUTABLE_GIT_METADATA)


def discover_protected_subpaths(work_dir: str) -> tuple[str, ...]:
    """Return the existing metadata paths below ``work_dir`` that the sandbox must keep read-only."""
    root = os.path.realpath(os.path.expanduser(work_dir))
    found: dict[str, None] = {}
    for repo in _candidate_repos(root):
        for path in _repo_paths(repo, root):
            found[path] = None
    return tuple(found)


def _candidate_repos(root: str) -> list[str]:
    repos = [root]
    try:
        with os.scandir(root) as entries:
            children = [e.path for e in entries if e.is_dir(follow_symlinks=False)]
    except OSError:
        return repos
    if len(children) > _MAX_CHILD_DIRS:
        logger.warning(
            "Workspace has %d child directories; only the first %d are checked for git metadata",
            len(children),
            _MAX_CHILD_DIRS,
        )
    return repos + children[:_MAX_CHILD_DIRS]


def _repo_paths(repo: str, root: str) -> list[str]:
    dot_git = os.path.join(repo, _DOT_GIT)
    paths: list[str] = []
    if os.path.islink(dot_git) or os.path.isfile(dot_git):
        # The pointer itself is protected too: rewriting it redirects git to a directory the sandbox controls.
        paths.append(dot_git)
        git_dir = _pointer_target(dot_git, repo)
    elif os.path.isdir(dot_git):
        git_dir = dot_git
    else:
        return paths
    for directory in _git_dirs(git_dir):
        if not is_within_boundary(directory, root):
            continue
        for name in _GIT_DIR_ENTRIES:
            entry = os.path.join(directory, name)
            if os.path.lexists(entry):
                paths.append(entry)
    return paths


def _pointer_target(dot_git: str, repo: str) -> str | None:
    """The git directory a ``.git`` link or ``gitdir:`` file points to, if it can be read."""
    if os.path.islink(dot_git):
        return os.path.realpath(dot_git)
    try:
        with open(dot_git, encoding="utf-8", errors="replace") as handle:
            first_line = handle.read(_POINTER_READ_BYTES).partition("\n")[0]
    except OSError:
        return None
    prefix = "gitdir:"
    if not first_line.startswith(prefix):
        return None
    return os.path.normpath(os.path.join(repo, first_line[len(prefix) :].strip()))


def _git_dirs(git_dir: str | None) -> list[str]:
    """A git directory plus the shared one a linked worktree names in ``commondir``."""
    if git_dir is None or not os.path.isdir(git_dir):
        return []
    directories = [git_dir]
    try:
        with open(os.path.join(git_dir, "commondir"), encoding="utf-8", errors="replace") as handle:
            common = handle.read(_POINTER_READ_BYTES).strip()
    except OSError:
        return directories
    if common:
        directories.append(os.path.normpath(os.path.join(git_dir, common)))
    return directories
