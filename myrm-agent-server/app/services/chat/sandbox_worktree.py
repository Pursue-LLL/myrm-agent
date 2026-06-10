"""[INPUT]
- app.services.chat.chat_service::ChatService (POS: Chat metadata persistence)

[OUTPUT]
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

logger = logging.getLogger(__name__)

_SANDBOX_DIR_NAME = ".sandboxes"


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
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


async def create_sandbox_worktree(
    base_dir: str,
    chat_id: str,
    branch_name: str | None = None,
) -> str | None:
    """Create an isolated git worktree for a chat sandbox session.

    Returns the absolute path to the worktree, or None on failure.
    The worktree is created from HEAD of the current branch.
    """
    if not await is_git_repository(base_dir):
        logger.warning("Cannot create sandbox worktree: %s is not a git repo", base_dir)
        return None

    worktree_dir = get_sandbox_worktree_path(base_dir, chat_id)

    if Path(worktree_dir).exists():
        logger.info("Sandbox worktree already exists at %s", worktree_dir)
        return worktree_dir

    effective_branch = branch_name or f"sandbox/chat-{chat_id[:12]}"

    try:
        os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "git",
                "worktree",
                "add",
                "--force",
                "-B",
                effective_branch,
                worktree_dir,
                "HEAD",
            ],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "git worktree add failed for chat sandbox (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return None

        logger.info(
            "Created sandbox worktree at %s (branch=%s) for chat %s",
            worktree_dir,
            effective_branch,
            chat_id[:8],
        )
        return worktree_dir
    except Exception as exc:
        logger.warning("Failed to create sandbox worktree for chat %s: %s", chat_id[:8], exc)
        return None


async def cleanup_sandbox_worktree(base_dir: str, chat_id: str) -> bool:
    """Remove the sandbox worktree and optionally its branch.

    Returns True if cleanup succeeded or worktree didn't exist.
    """
    worktree_dir = get_sandbox_worktree_path(base_dir, chat_id)

    if not Path(worktree_dir).exists():
        return True

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "remove", "--force", worktree_dir],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Cleaned up sandbox worktree at %s for chat %s", worktree_dir, chat_id[:8])

            branch_name = f"sandbox/chat-{chat_id[:12]}"
            await asyncio.to_thread(
                subprocess.run,
                ["git", "branch", "-D", branch_name],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return True
        else:
            logger.warning(
                "git worktree remove failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return False
    except Exception as exc:
        logger.warning("Failed to cleanup sandbox worktree for chat %s: %s", chat_id[:8], exc)
        return False


async def merge_sandbox_to_parent(base_dir: str, chat_id: str) -> tuple[bool, str]:
    """Merge sandbox branch changes back to the parent branch.

    Returns (success, message) tuple.
    """
    branch_name = f"sandbox/chat-{chat_id[:12]}"

    parent_branch = await _get_current_branch(base_dir)
    if not parent_branch:
        return False, "Cannot determine parent branch"

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "merge", "--no-ff", branch_name, "-m", f"Merge sandbox session {chat_id[:8]}"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            await cleanup_sandbox_worktree(base_dir, chat_id)
            return True, f"Successfully merged sandbox to {parent_branch}"
        else:
            return False, f"Merge conflict: {result.stderr.strip()}"
    except Exception as exc:
        return False, f"Merge failed: {exc}"
