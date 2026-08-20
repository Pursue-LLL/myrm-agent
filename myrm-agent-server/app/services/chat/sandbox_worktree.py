"""[INPUT]
- app.services.chat.chat_service::ChatService (POS: Chat metadata persistence)
- app.core.utils.git_worktree (POS: 共享 git worktree 命令基础设施与错误类型——worktree add/remove/分支删除/merge 组合、per-base_dir merge 锁、git identity 兜底、auto-commit、dirty 检测、WorktreeCreateError/WorktreeErrorReason/_classify_git_error)

[OUTPUT]
- _sandbox_branch_name: Deterministic per-chat sandbox branch name (single source of truth).
- create_sandbox_worktree: Create an isolated git worktree for a chat sandbox session.
- cleanup_sandbox_worktree: Remove the sandbox worktree when session ends.
- get_sandbox_worktree_path: Compute the deterministic path for a chat's sandbox worktree.
- is_git_repository: Check if a directory is within a git repository.
- merge_sandbox_to_parent: Merge sandbox branch changes back to the source branch.

[POS]
Shared git worktree lifecycle management for chat sandbox sessions.
Used by the chat parameter converter and sandbox API endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from app.core.utils.git_worktree import (
    _GIT_ENV,
    WorktreeCreateError,
    WorktreeErrorReason,
    _auto_commit_dirty_worktree,
    _delete_git_branch,
    _get_merge_lock,
    _git_worktree_add,
    _merge_branch_into_current,
    _remove_worktree,
    _worktree_is_dirty,
)

logger = logging.getLogger(__name__)

_SANDBOX_DIR_NAME = ".sandboxes"


def _sandbox_branch_name(chat_id: str) -> str:
    """Deterministic per-chat sandbox branch name (single source of truth)."""
    return f"sandbox/chat-{chat_id[:12]}"


def get_sandbox_worktree_path(base_dir: str, chat_id: str) -> str:
    """Compute the deterministic worktree path for a chat sandbox."""
    safe_id = chat_id.replace("/", "-").replace("\\", "-")
    return os.path.join(base_dir, _SANDBOX_DIR_NAME, f"sandbox-{safe_id[:12]}")


async def is_git_repository(directory: str) -> bool:
    """Check if directory is inside a git work tree."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
            env=_GIT_ENV,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False


async def _get_current_branch(base_dir: str) -> str | None:
    """Get current branch name of base_dir."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env=_GIT_ENV,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


async def create_sandbox_worktree(base_dir: str, chat_id: str) -> str | WorktreeCreateError:
    """Create an isolated git worktree for a chat sandbox session.

    Returns the absolute path to the worktree on success,
    or a WorktreeCreateError with structured reason on failure.
    """
    if not await is_git_repository(base_dir):
        return WorktreeCreateError(
            reason=WorktreeErrorReason.NOT_GIT_REPO,
            message=f"{base_dir} is not a git repository",
        )

    worktree_dir = get_sandbox_worktree_path(base_dir, chat_id)

    if Path(worktree_dir).exists():
        logger.info("Sandbox worktree already exists at %s", worktree_dir)
        return worktree_dir

    return await _git_worktree_add(
        base_dir,
        _sandbox_branch_name(chat_id),
        worktree_dir,
        _SANDBOX_DIR_NAME,
        context="chat sandbox",
    )


async def cleanup_sandbox_worktree(base_dir: str, chat_id: str, *, force: bool = False) -> bool:
    """Remove the sandbox worktree and its branch.

    Default safe mode checks for uncommitted changes first and keeps the
    worktree when it is dirty, so ending a chat session never silently drops
    file-tool edits the agent never committed.  ``force=True`` (used after a
    successful merge, or when the user explicitly discards the sandbox)
    deletes unconditionally.  Returns True if the worktree was removed or
    absent; False when preserved due to dirtiness.
    """
    worktree_dir = get_sandbox_worktree_path(base_dir, chat_id)

    if not Path(worktree_dir).exists():
        return True

    if not force and await _worktree_is_dirty(worktree_dir):
        logger.warning(
            "Sandbox worktree %s for chat %s has uncommitted changes; preserved "
            "for manual handling instead of deleting (would lose data)",
            worktree_dir,
            chat_id[:8],
        )
        return False

    if await _remove_worktree(base_dir, worktree_dir, context="sandbox"):
        await _delete_git_branch(base_dir, _sandbox_branch_name(chat_id))
        return True
    return False


async def merge_sandbox_to_parent(base_dir: str, chat_id: str) -> tuple[bool, str]:
    """Merge sandbox branch changes back to the parent branch.

    Returns (success, message) tuple.  Merges on the same base_dir are
    serialized with kanban merges so git's shared index is never written
    concurrently.
    """
    async with _get_merge_lock(base_dir):
        return await _merge_sandbox_to_parent_locked(base_dir, chat_id)


async def _merge_sandbox_to_parent_locked(base_dir: str, chat_id: str) -> tuple[bool, str]:
    branch_name = _sandbox_branch_name(chat_id)

    parent_branch = await _get_current_branch(base_dir)
    if not parent_branch:
        return False, "Cannot determine parent branch"

    worktree_path = get_sandbox_worktree_path(base_dir, chat_id)
    if Path(worktree_path).exists():
        if not await _auto_commit_dirty_worktree(worktree_path):
            # Auto-commit was rejected (e.g. pre-commit hook); merging would
            # drop the uncommitted edits when cleanup runs, so preserve the
            # worktree and let the user handle it instead.
            logger.warning(
                "Cannot commit dirty sandbox worktree %s for chat %s; merge skipped, worktree preserved",
                worktree_path,
                chat_id[:8],
            )
            return False, "Sandbox has uncommitted changes that could not be committed"

    success, conflicts, stderr = await _merge_branch_into_current(base_dir, branch_name, f"Merge sandbox session {chat_id[:8]}")
    if success:
        await cleanup_sandbox_worktree(base_dir, chat_id, force=True)
        return True, f"Successfully merged sandbox to {parent_branch}"
    if conflicts:
        return False, f"Merge conflict in {len(conflicts)} file(s)"
    # Non-conflict merge failure (e.g. rejected by a merge hook); surface the
    # actual reason so the user is not told it was a conflict.
    return False, f"Merge failed: {stderr[:200]}" if stderr else "Merge failed"
