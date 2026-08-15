"""Git command helpers for merging a task worktree back into its target branch.

[INPUT]
- worktree (POS: worktree_dir / branch-name resolution + merge orchestration)
- app.services.chat._git_shared (POS: shared git environment `_GIT_ENV`)

[OUTPUT]
- _branch_has_commits, _ensure_target_branch_checked_out, _is_valid_git_branch

[POS]
合并前的 git 前置步骤：判断是否有可合并提交、确保 merge 落在目标分支、校验分支名。
自动提交未提交改动的共享实现位于 _git_shared（kanban 与 sandbox 共用一份，
避免语义漂移）。与 worktree.py 解耦，避免主文件超行数预算。
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess

from app.services.chat._git_shared import _GIT_ENV

logger = logging.getLogger(__name__)


def _is_valid_git_branch(name: str) -> bool:
    """True when ``name`` is a git-ref-format-valid branch name.

    Mirrors the core rules of ``git check-ref-format``: no leading ``-``
    (would be parsed as a CLI option), no spaces, no ``~^:?*[\\`` or ``..``,
    not empty.  Slashes are allowed, so nested names like ``feature/x`` pass.
    """
    if not name or name.startswith("-"):
        return False
    if re.search(r"[ ~\^:?*\[\]\\]", name):
        return False
    if ".." in name or name.endswith("."):
        return False
    if name.startswith("/") or name.endswith("/") or "//" in name:
        return False
    return True


async def _branch_has_commits(base_dir: str, branch: str, target_branch: str) -> bool:
    """Check whether a worktree branch has commits ahead of its merge target.

    ``git rev-list --count target..branch`` counts commits on ``branch`` not
    reachable from ``target``; a non-zero count means the merge would add
    something.  Falls back to True so a failed lookup never silently skips a
    merge that should happen.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "git",
                "rev-list",
                "--count",
                "--end-of-options",
                f"{target_branch}..{branch}",
            ],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            return True
        return result.stdout.strip() != "0"
    except Exception:
        return True


async def _ensure_target_branch_checked_out(base_dir: str, target_branch: str) -> bool:
    """Ensure the merge target branch is checked out in base_dir.

    A task's target branch is normally the repo's current branch, but an
    explicit target branch may differ.  Check it out (creating it from HEAD
    on first use) so the merge lands on the branch the user asked for.
    Returns True when base_dir is on the target branch.

    Unusable branch names (starting with ``-`` or containing git-forbidden
    characters) are rejected rather than fed to ``git checkout``, where they
    would be parsed as options — the caller preserves the worktree instead.
    """
    if not _is_valid_git_branch(target_branch):
        logger.warning("Unusable target branch %r; merge skipped", target_branch)
        return False
    try:
        current = await asyncio.to_thread(
            subprocess.run,
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if current.returncode == 0 and current.stdout.strip() == target_branch:
            return True

        branch_exists = await asyncio.to_thread(
            subprocess.run,
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target_branch}"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        checkout = (
            ["git", "checkout", target_branch]
            if branch_exists.returncode == 0
            else ["git", "checkout", "-b", target_branch]
        )
        result = await asyncio.to_thread(
            subprocess.run,
            checkout,
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            logger.warning(
                "Failed to switch base_dir to target branch %s: %s",
                target_branch,
                result.stderr.strip()[:200],
            )
            return False
        return True
    except Exception as exc:
        logger.warning("Failed to ensure target branch %s: %s", target_branch, exc)
        return False
