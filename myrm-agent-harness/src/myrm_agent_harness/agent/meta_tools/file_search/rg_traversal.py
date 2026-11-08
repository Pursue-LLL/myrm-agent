"""ripgrep traversal policy shared by glob_tool and grep_tool.

[INPUT]
- fallback_discovery::DEFAULT_PRUNED_DIR_NAMES, VCS_DIR_NAMES, VCS_EXCLUDE_GLOB (POS: 候选文件发现策略：Python 档发现 + 两档共用的目录排除名单)

[OUTPUT]
- rg_traversal_args: ripgrep flags that apply the Python tier's file-selection policy to its walk

[POS]
Single place that decides which files ripgrep walks, so the ripgrep tier follows the file-selection policy of the
Python tier (``fallback_discovery``): user configuration never applies, hidden files are walked and
version-control internals are never listed. A git checkout keeps its repository boundary, as it has in git: the
ignore files above its top level never apply, and neither do the rules of a repository around a nested one. A folder
outside any repository (no ``.git`` above it, or only a directory that ignores everything below itself between it and
the checkout) is walked without one: dependency and build directories are skipped and neither the ignore files of
parent directories nor the user's global ignore file are honoured.
"""

from __future__ import annotations

import os
from pathlib import Path

from .fallback_discovery import DEFAULT_PRUNED_DIR_NAMES, VCS_DIR_NAMES, VCS_EXCLUDE_GLOB

# The trailing slash limits the exclusion to directories: a file that merely shares a name, such as ``docs/build``,
# stays searchable.
_PRUNE_DIRECTORIES_GLOB = "!{" + ",".join(sorted(DEFAULT_PRUNED_DIR_NAMES - VCS_DIR_NAMES)) + "}/"

# The rules that ignore everything below the directory holding the ``.gitignore`` they stand in.
_CATCH_ALL_RULES = frozenset({b"*", b"/*", b"**", b"/**", b"**/*"})
_UTF8_BOM = b"\xef\xbb\xbf"


def _ignores_everything_below(gitignore: Path) -> bool:
    """Whether ``gitignore`` ignores all that lies below its directory and takes nothing back.

    A virtual environment, a tool cache or a build output writes such a file into the directory it owns. The file is
    read the way git reads it: a line ends at a line feed, one carriage return before it and the trailing spaces (and
    only those) are dropped, and so is a byte-order mark at the start of the file. A negation anywhere may bring files
    back, so a file that holds one does not count.
    """
    if not os.path.isfile(gitignore):  # opening a FIFO would block the event loop for good
        return False
    try:
        content = gitignore.read_bytes()
    except OSError:
        return False
    rules = [line.removesuffix(b"\r").rstrip(b" ") for line in content.removeprefix(_UTF8_BOM).split(b"\n")]
    return any(rule in _CATCH_ALL_RULES for rule in rules) and not any(rule.startswith(b"!") for rule in rules)


def _walks_outside_a_repository(search_root: Path) -> bool:
    """Whether ``search_root`` is walked as a folder that no repository governs.

    That holds when no checkout encloses it, and below a directory that ignores everything below itself: version
    control owns none of those files and git lists nothing in them, so the root is searched the way the Python tier
    searches a root that git ignores. Only the directories between the root and the top level of its checkout decide
    this; the ``.gitignore`` of the root, of the top level and of anything above it is never read.
    """
    # ``os.path`` answers False where ``Path`` raises (a path beyond the platform's length limit): such an entry is no
    # checkout, and a flag computation must not fail the call.
    if os.path.exists(search_root / ".git"):
        return False
    between: list[Path] = []
    for directory in search_root.parents:
        if os.path.exists(directory / ".git"):  # a directory, or a file in worktrees and submodules
            return any(_ignores_everything_below(candidate / ".gitignore") for candidate in between)
        between.append(directory)
    return True


def rg_traversal_args(search_root: Path, *, include_ignored: bool = False) -> list[str]:
    """Flags for the ripgrep walk below ``search_root``; ``include_ignored`` lists ignored files too."""
    args = ["--no-config", "--hidden", "--glob", VCS_EXCLUDE_GLOB]
    if include_ignored:
        args.append("--no-ignore")
    elif _walks_outside_a_repository(search_root):
        # ``--no-require-git`` makes ripgrep honour ``.gitignore`` files without a repository, and it also reads
        # those of parent directories and the user's global ignore file (``core.excludesFile``): a stray ``*`` in
        # either would hide the whole workspace, and the Python tier reads neither outside a checkout. Inside a
        # checkout the flag is left off: with it ripgrep applies the ignore files of every directory above the
        # search root, up to the file system root, and a repository around a nested one would hide its files.
        args.extend(["--no-require-git", "--no-ignore-parent", "--no-ignore-global", "--glob", _PRUNE_DIRECTORIES_GLOB])
    return args
