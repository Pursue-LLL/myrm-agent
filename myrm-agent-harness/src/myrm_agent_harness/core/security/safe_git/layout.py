"""Proof that the repository git would use for a directory is that directory's own.

[INPUT]
- query: GitHardeningError / query_git (POS: the refusal and the one ``git rev-parse`` that settles a layout the file system alone cannot)

[OUTPUT]
- LexicalLayout: verdict read from the file system alone (no git process): own, foreign, absent or unknown
- lexical_layout: walk up from a directory exactly as git discovers a repository and classify the first ``.git`` found
- require_resolved_layout: settle the unknown and ``core.worktree`` cases with git's own answer; ``GitHardeningError`` when the layout is not the directory's own

[POS]
git does not record which directory owns a git directory, so a folder that arrives with a ``.git`` symlink, a ``.git``
file naming another repository, a ``commondir`` file or a ``core.worktree`` can aim a command at another repository's
branches, index and files (a ``commit`` then moves *that* repository's ``main``). Accepted layouts: a ``.git`` directory
holding the repository; a linked worktree (``.git`` file -> ``<common>/worktrees/<name>``, whose ``gitdir`` file names
that same ``.git`` file); a submodule checkout (the git directory's ``core.worktree`` leads back to the checkout); a bare
repository the directory sits in. A separate git directory (``git init --separate-git-dir``) is indistinguishable from a
hostile ``.git`` file and is refused with the rest. The two layouts the application itself creates (ordinary repository,
linked worktree) are proved by reading files only, so they cost no git process.
"""

from __future__ import annotations

import enum
import os
from collections.abc import Mapping

from .query import GitHardeningError, query_git

__all__ = ["LexicalLayout", "lexical_layout", "require_resolved_layout"]

_GITFILE_PREFIX = "gitdir:"
_POINTER_MAX_BYTES = 4096
# Variables that make git skip or limit its discovery, so a walk up the tree no longer says which repository it uses.
_DISCOVERY_VARIABLES = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CEILING_DIRECTORIES"})
_RESOLUTION_QUERY = ("rev-parse", "--is-bare-repository", "--absolute-git-dir", "--git-common-dir", "--show-toplevel")


class LexicalLayout(enum.Enum):
    OWN = enum.auto()  # a layout this module proves from files alone
    FOREIGN = enum.auto()  # a layout that aims git at another repository
    ABSENT = enum.auto()  # no repository above the directory: git itself will say so
    UNKNOWN = enum.auto()  # git has to answer


def _same(first: str, second: str) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _is_link(path: str) -> bool:
    return os.path.islink(path) or os.path.isjunction(path)


def _first_line(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            return os.fsdecode(handle.read(_POINTER_MAX_BYTES)).split("\n", 1)[0].strip()
    except OSError:
        return None


def _gitfile_target(dot_git: str) -> str | None:
    """The directory a ``.git`` file names (relative to the file's own folder), ``None`` if it is not a gitfile."""
    first_line = _first_line(dot_git)
    if first_line is None or not first_line.startswith(_GITFILE_PREFIX):
        return None
    return os.path.join(os.path.dirname(dot_git), first_line[len(_GITFILE_PREFIX) :].strip())


def _is_linked_worktree(dot_git: str, admin_dir: str) -> bool:
    """``admin_dir`` is ``<common>/worktrees/<name>`` and records this very ``.git`` file as the worktree it serves."""
    commondir = _first_line(os.path.join(admin_dir, "commondir"))
    recorded = _first_line(os.path.join(admin_dir, "gitdir"))
    if commondir is None or recorded is None:
        return False
    worktrees = os.path.join(admin_dir, commondir, "worktrees")
    return _same(os.path.dirname(admin_dir), worktrees) and _same(os.path.join(admin_dir, recorded), dot_git)


def _looks_like_git_dir(path: str) -> bool:
    """git also takes a directory that is itself a git directory (a bare repository) as the repository."""
    if not os.path.isfile(os.path.join(path, "HEAD")):
        return False
    return os.path.lexists(os.path.join(path, "commondir")) or (
        os.path.isdir(os.path.join(path, "objects")) and os.path.isdir(os.path.join(path, "refs"))
    )


def _classify_dot_git(dot_git: str) -> LexicalLayout:
    if _is_link(dot_git):
        return LexicalLayout.FOREIGN
    if os.path.isdir(dot_git):
        if os.path.lexists(os.path.join(dot_git, "commondir")):
            return LexicalLayout.FOREIGN
        return LexicalLayout.OWN if os.path.isfile(os.path.join(dot_git, "HEAD")) else LexicalLayout.UNKNOWN
    target = _gitfile_target(dot_git)
    if target is None:
        return LexicalLayout.FOREIGN
    if os.path.lexists(os.path.join(target, "commondir")):
        return LexicalLayout.OWN if _is_linked_worktree(dot_git, target) else LexicalLayout.FOREIGN
    return LexicalLayout.UNKNOWN


def lexical_layout(directory: str, env: Mapping[str, str] | None) -> LexicalLayout:
    """Classify the repository git discovers from *directory* (an absolute, symlink-free path) without running git."""
    if _DISCOVERY_VARIABLES.intersection(os.environ if env is None else env):
        return LexicalLayout.UNKNOWN
    current = directory
    while True:
        dot_git = os.path.join(current, ".git")
        if os.path.lexists(dot_git):
            return _classify_dot_git(dot_git)
        if _looks_like_git_dir(current):
            # A bare repository can carry a ``commondir`` file too, so the walk must not slide past it.
            return LexicalLayout.UNKNOWN
        parent = os.path.dirname(current)
        if parent == current:
            return LexicalLayout.ABSENT
        current = parent


def _inside(directory: str, git_dir: str) -> bool:
    try:
        return os.path.commonpath((os.path.realpath(directory), os.path.realpath(git_dir))) == os.path.realpath(git_dir)
    except ValueError:
        return False


def _work_tree_is_own(work_tree: str, git_dir: str, common_dir: str, *, names_worktree: bool) -> bool:
    dot_git = os.path.join(work_tree, ".git")
    if _is_link(dot_git):
        return False
    if os.path.isdir(dot_git):
        return _same(dot_git, git_dir) and _same(common_dir, git_dir)
    target = _gitfile_target(dot_git)
    if target is None or not _same(target, git_dir):
        return False
    # A submodule's git directory names its checkout through ``core.worktree``; any other file pointer is foreign.
    return _is_linked_worktree(dot_git, git_dir) or (names_worktree and _same(common_dir, git_dir))


def require_resolved_layout(directory: str, env: Mapping[str, str] | None, *, names_worktree: bool) -> None:
    """Refuse unless git's own answer shows the repository serving *directory* is that directory's own.

    *names_worktree* is whether the repository's configuration sets ``core.worktree``.
    """
    completed = query_git(directory, env, _RESOLUTION_QUERY, purpose="locate the repository's git directory")
    lines = completed.stdout.decode("utf-8", "surrogateescape").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 3 or len(lines) > 4:
        if names_worktree or len(lines) > 4:
            raise GitHardeningError(f"Cannot locate the work tree of the repository in {directory}")
        return  # not a repository: the command fails on its own
    is_bare, git_dir, common_dir = lines[:3]
    common_dir = os.path.join(directory, common_dir)
    if is_bare == "true" or len(lines) == 3:
        # No work tree: the directory is the git directory or sits inside it, and a configured work tree is an attack.
        own = not names_worktree and _inside(directory, git_dir) and _same(common_dir, git_dir)
    else:
        own = _work_tree_is_own(lines[3], git_dir, common_dir, names_worktree=names_worktree)
    if not own:
        raise GitHardeningError(f"The git repository serving {directory} does not belong to that directory: {lines!r}")
