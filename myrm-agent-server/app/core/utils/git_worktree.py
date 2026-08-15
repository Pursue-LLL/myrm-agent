"""Shared git command helpers for worktree lifecycle (sandbox + kanban).

[INPUT]
- (none; stdlib only)

[OUTPUT]
- _GIT_ENV: C-locale git environment for subprocess calls.
- _get_merge_lock: Per-base_dir merge lock shared across kanban/sandbox merges.
- _git_identity: Per-repo ``-c user.name/-c user.email`` overrides for missing identity.
- _auto_commit_dirty_worktree: Commit uncommitted worktree edits before a merge.
- _collect_conflict_files: List files with unresolved merge conflicts.
- _abort_merge: Roll back an in-progress merge so the repo stays usable.
- _worktree_is_dirty: Fail-closed dirty check for a worktree.
- WorktreeErrorReason / WorktreeCreateError: Structured worktree creation error types.
- _classify_git_error: Map git stderr to a WorktreeErrorReason.

[POS]
通用工具层的共享 git worktree 命令基础设施：sandbox 与 kanban 的 worktree
生命周期共用同一份实现，避免两处语义漂移。被 chat.sandbox_worktree 与
kanban task_runner 直接引用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# C-locale environment so git output stays byte-stable regardless of the
# host locale (Chinese/other locales would otherwise localize git messages).
_GIT_ENV: dict[str, str] = {**os.environ, "LANG": "C", "LC_ALL": "C"}

# Per-base_dir merge locks shared by kanban and sandbox.  Git writes the
# shared index in base_dir, so concurrent merges on the same repo race
# (observed "Unable to write index").  Serialize per base_dir so unrelated
# repos merge in parallel while same-repo merges are mutually exclusive.
_MERGE_LOCKS: dict[str, asyncio.Lock] = {}


def _get_merge_lock(base_dir: str) -> asyncio.Lock:
    lock = _MERGE_LOCKS.get(base_dir)
    if lock is None:
        lock = asyncio.Lock()
        _MERGE_LOCKS[base_dir] = lock
    return lock


async def _worktree_is_dirty(path: str) -> bool:
    """True when a worktree has uncommitted changes (untracked, modified, staged)."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        # Fail-closed: an unreachable git status must not let cleanup force-delete
        # a worktree that may hold uncommitted agent edits.
        return True


async def _git_identity(repo_dir: str) -> list[str]:
    """Return ``-c key=value`` overrides for identity keys missing on the repo.

    Fresh ``git init``/``git clone`` repos often have no user identity
    configured, which makes ``git commit`` fail with "Please tell me who you
    are".  Each key (``user.name``/``user.email``) is checked against the
    repo's own config (local + global) and only the missing ones are injected,
    so a configured author is never overwritten.
    """
    overrides: list[str] = []
    for key, fallback in (
        ("user.name", "Myrm Agent"),
        ("user.email", "agent@myrm.local"),
    ):
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "config", "--get", key],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=5,
                env=_GIT_ENV,
            )
            if result.returncode == 0 and result.stdout.strip():
                continue
        except Exception:
            return []
        overrides.extend(("-c", f"{key}={fallback}"))
    return overrides


async def _auto_commit_dirty_worktree(
    worktree_path: str, *, commit_message: str = "Auto-commit before merge"
) -> bool:
    """Commit uncommitted changes in a worktree before merging it back.

    Returns True when the worktree is clean (nothing to commit) or the
    auto-commit succeeded.  Returns False when there are uncommitted changes
    that could not be committed — the caller must preserve the worktree
    instead of cleaning it up, or the agent's edits would be silently lost.

    ``commit_message`` lets the caller stamp the auto-commit with its own
    context (e.g. sandbox session vs kanban task) so git history stays
    accurate when this shared helper is reused.
    """
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
            return status.returncode == 0

        add_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "add", "-A"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if add_result.returncode != 0:
            logger.warning(
                "git add -A failed in worktree %s: %s",
                worktree_path,
                add_result.stderr.strip()[:200],
            )
            return False

        identity = await _git_identity(worktree_path)
        commit = await asyncio.to_thread(
            subprocess.run,
            ["git", *identity, "commit", "-m", commit_message],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=15,
            env=_GIT_ENV,
        )
        if commit.returncode == 0:
            logger.info("Auto-committed dirty worktree at %s", worktree_path)
            return True
        logger.warning(
            "Auto-commit failed in worktree %s: %s",
            worktree_path,
            commit.stderr.strip()[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Auto-commit failed for %s: %s", worktree_path, exc)
        return False


async def _collect_conflict_files(base_dir: str) -> list[str]:
    """List files with unresolved merge conflicts in base_dir, or [] when none."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        return []


async def _abort_merge(base_dir: str) -> None:
    """Roll back an in-progress merge so base_dir stays usable.

    Logs a warning when the abort itself fails (other than the benign
    "no merge to abort" case) so a lingering MERGE_HEAD that would block
    every later merge on the repo is not silently missed.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "merge", "--abort"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=15,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "MERGE_HEAD missing" not in stderr:
                logger.warning(
                    "git merge --abort failed in %s (rc=%d): %s",
                    base_dir,
                    result.returncode,
                    stderr[:200],
                )
    except Exception as exc:
        logger.warning("Failed to abort merge in %s: %s", base_dir, exc)


class WorktreeErrorReason(str, Enum):
    BRANCH_EXISTS = "branch-exists"
    ALREADY_CHECKED_OUT = "already-checked-out"
    PATH_EXISTS = "path-exists"
    NOT_GIT_REPO = "not-git-repo"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class WorktreeCreateError:
    reason: WorktreeErrorReason
    message: str = ""


def _classify_git_error(stderr: str) -> WorktreeErrorReason:
    """Map git stderr to a structured error reason."""
    lower = stderr.lower()
    if "already checked out" in lower:
        return WorktreeErrorReason.ALREADY_CHECKED_OUT
    if "already exists" in lower and "branch" in lower:
        return WorktreeErrorReason.BRANCH_EXISTS
    if "already exists" in lower:
        return WorktreeErrorReason.PATH_EXISTS
    return WorktreeErrorReason.ERROR
