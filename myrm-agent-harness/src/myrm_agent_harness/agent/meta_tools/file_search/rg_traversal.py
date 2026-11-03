"""ripgrep traversal policy shared by glob_tool and grep_tool.

[INPUT]
- fallback_discovery::DEFAULT_PRUNED_DIR_NAMES, VCS_DIR_NAMES, VCS_EXCLUDE_GLOB (POS: 候选文件发现策略：Python 档发现 + 两档共用的目录排除名单)

[OUTPUT]
- has_git_ancestor: Whether a directory lies inside a git checkout
- rg_traversal_args: ripgrep flags that make its walk select the files the Python tier would

[POS]
Single place that decides which files ripgrep walks, so the ripgrep tier and the Python tier
(``fallback_discovery``) search the same files: user configuration never applies, hidden files are walked,
version-control internals are never listed, and in a plain folder (no ``.git`` above it) dependency and build
directories are skipped and ignore files of parent directories are not honoured. Inside a git checkout the
decision stays with git's own ignore rules.
"""

from __future__ import annotations

from pathlib import Path

from .fallback_discovery import DEFAULT_PRUNED_DIR_NAMES, VCS_DIR_NAMES, VCS_EXCLUDE_GLOB

# The trailing slash limits the exclusion to directories: a file that merely shares a name, such as ``docs/build``,
# stays searchable.
_PRUNE_DIRECTORIES_GLOB = "!{" + ",".join(sorted(DEFAULT_PRUNED_DIR_NAMES - VCS_DIR_NAMES)) + "}/"


def has_git_ancestor(path: Path) -> bool:
    """Whether ``path`` or one of its parents holds ``.git`` (a directory, or a file in worktrees and submodules)."""
    return any((candidate / ".git").exists() for candidate in (path, *path.parents))


def rg_traversal_args(search_root: Path, *, include_ignored: bool = False) -> list[str]:
    """Flags for the ripgrep walk below ``search_root``; ``include_ignored`` lists ignored files too."""
    args = ["--no-config", "--hidden", "--no-require-git", "--glob", VCS_EXCLUDE_GLOB]
    if include_ignored:
        args.append("--no-ignore")
    elif not has_git_ancestor(search_root):
        # ``--no-require-git`` makes ripgrep honour ``.gitignore`` files without a repository, and it also reads
        # those of parent directories: a stray ``*`` in one of them would hide the whole workspace.
        args.extend(["--no-ignore-parent", "--glob", _PRUNE_DIRECTORIES_GLOB])
    return args
