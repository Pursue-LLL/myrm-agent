"""[INPUT]
- app.services.chat.chat_service::ChatService (POS: Chat metadata persistence)

[OUTPUT]
- create_sandbox_worktree: Create an isolated git worktree for a chat sandbox session.
- cleanup_sandbox_worktree: Remove the sandbox worktree when session ends.
- get_sandbox_worktree_path: Compute the deterministic path for a chat's sandbox worktree.
- is_git_repository: Check if a directory is within a git repository.
- merge_sandbox_to_parent: Merge sandbox branch changes back to the source branch.
- prune_stale_sandboxes: Startup cleanup for orphaned worktrees and branches.
- WorktreeCreateError: Structured error type for worktree creation failures.

[POS]
Shared git worktree lifecycle management for chat sandbox sessions.
Used by the chat parameter converter and sandbox API endpoints.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

_SANDBOX_DIR_NAME = ".sandboxes"

_GIT_ENV: dict[str, str] = {**os.environ, "LANG": "C", "LC_ALL": "C"}


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


def _ensure_worktrees_excluded(base_dir: str) -> None:
    """Ensure .sandboxes/ is listed in .git/info/exclude so git status stays clean."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            return
        common_dir = result.stdout.strip()
        exclude_path = os.path.join(common_dir, "info", "exclude")

        line = f"/{_SANDBOX_DIR_NAME}/"
        current = ""
        try:
            current = Path(exclude_path).read_text(encoding="utf-8")
        except OSError:
            pass

        if any(l.strip() == line for l in current.split("\n")):
            return

        prefix = "\n" if current and not current.endswith("\n") else ""
        with open(exclude_path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{line}\n")
    except Exception:
        pass


async def create_sandbox_worktree(
    base_dir: str,
    chat_id: str,
    branch_name: str | None = None,
) -> str | WorktreeCreateError:
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

    effective_branch = branch_name or f"sandbox/chat-{chat_id[:12]}"

    try:
        os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)
        _ensure_worktrees_excluded(base_dir)

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
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            reason = _classify_git_error(stderr)
            logger.warning(
                "git worktree add failed for chat sandbox (rc=%d, reason=%s): %s",
                result.returncode,
                reason.value,
                stderr[:300],
            )
            return WorktreeCreateError(reason=reason, message=stderr[:300])

        logger.info(
            "Created sandbox worktree at %s (branch=%s) for chat %s",
            worktree_dir,
            effective_branch,
            chat_id[:8],
        )
        return worktree_dir
    except Exception as exc:
        logger.warning("Failed to create sandbox worktree for chat %s: %s", chat_id[:8], exc)
        return WorktreeCreateError(reason=WorktreeErrorReason.ERROR, message=str(exc)[:300])


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
            env=_GIT_ENV,
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
                env=_GIT_ENV,
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
            env=_GIT_ENV,
        )
        if result.returncode == 0:
            await cleanup_sandbox_worktree(base_dir, chat_id)
            return True, f"Successfully merged sandbox to {parent_branch}"
        else:
            return False, f"Merge conflict: {result.stderr.strip()}"
    except Exception as exc:
        return False, f"Merge failed: {exc}"


async def prune_stale_sandboxes(base_dir: str) -> int:
    """Startup cleanup: prune dead worktree references and remove orphaned sandbox branches.

    Returns the number of stale branches removed.
    """
    if not await is_git_repository(base_dir):
        return 0

    try:
        await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "prune"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
    except Exception:
        pass

    removed = 0
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "branch", "--list", "sandbox/*"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        if result.returncode != 0:
            return 0

        wt_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "list", "--porcelain"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=10,
            env=_GIT_ENV,
        )
        active_branches: set[str] = set()
        if wt_result.returncode == 0:
            for line in wt_result.stdout.split("\n"):
                if line.startswith("branch refs/heads/"):
                    active_branches.add(line.removeprefix("branch refs/heads/"))

        for line in result.stdout.strip().split("\n"):
            branch = line.strip().removeprefix("* ")
            if not branch or branch in active_branches:
                continue
            del_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "branch", "-D", branch],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=5,
                env=_GIT_ENV,
            )
            if del_result.returncode == 0:
                removed += 1
    except Exception as exc:
        logger.debug("prune_stale_sandboxes partial failure: %s", exc)

    if removed > 0:
        logger.info("Pruned %d stale sandbox branches in %s", removed, base_dir)
    return removed
