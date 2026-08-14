"""Git command helpers for merging a task worktree back into its target branch.

[INPUT]
- worktree (POS: worktree_dir / branch-name resolution + merge orchestration)

[OUTPUT]
- _auto_commit_dirty_worktree, _branch_has_commits, _ensure_target_branch_checked_out

[POS]
合并前的 git 前置步骤：自动提交 worktree 内未提交改动、判断是否有可合并提交、
确保 merge 落在目标分支。与 worktree.py 解耦，避免主文件超行数预算。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

from app.services.chat.sandbox_worktree import _GIT_ENV

logger = logging.getLogger(__name__)


async def _auto_commit_dirty_worktree(worktree_path: str) -> None:
    """Commit uncommitted changes in a worktree before merging it back."""
    try:
        status = await asyncio.to_thread(
            subprocess.run,
            ["git", "status", "--porcelain"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if status.returncode != 0 or not status.stdout.strip():
            return
        await asyncio.to_thread(
            subprocess.run,
            ["git", "add", "-A"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        commit = await asyncio.to_thread(
            subprocess.run,
            ["git", "commit", "-m", "Kanban task auto-commit before merge"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=15,
            env=_GIT_ENV,
        )
        if commit.returncode == 0:
            logger.info("Auto-committed dirty worktree at %s", worktree_path)
    except Exception as exc:
        logger.debug("Auto-commit failed for %s: %s", worktree_path, exc)


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
            ["git", "rev-list", "--count", f"{target_branch}..{branch}"],
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
    """
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
