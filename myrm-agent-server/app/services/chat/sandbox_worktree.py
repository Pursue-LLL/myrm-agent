"""[INPUT]
- app.services.chat.chat_service::ChatService (POS: Chat metadata persistence)

[OUTPUT]
- create_sandbox_worktree: Create an isolated git worktree for a chat sandbox session.
- cleanup_sandbox_worktree: Remove the sandbox worktree when session ends.
- get_sandbox_worktree_path: Compute the deterministic path for a chat's sandbox worktree.
- is_git_repository: Check if a directory is within a git repository.
- merge_sandbox_to_parent: Merge sandbox branch changes back to the source branch.
- _get_merge_lock: Shared per-base_dir merge lock reused by kanban task merges.
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

        if any(existing_line.strip() == line for existing_line in current.split("\n")):
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
        logger.warning(
            "Failed to create sandbox worktree for chat %s: %s", chat_id[:8], exc
        )
        return WorktreeCreateError(
            reason=WorktreeErrorReason.ERROR, message=str(exc)[:300]
        )


async def _worktree_is_dirty(path: str) -> bool:
    """True when a sandbox worktree has uncommitted changes (untracked, modified, staged)."""
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


async def cleanup_sandbox_worktree(
    base_dir: str, chat_id: str, *, force: bool = False
) -> bool:
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
            logger.info(
                "Cleaned up sandbox worktree at %s for chat %s",
                worktree_dir,
                chat_id[:8],
            )

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
        logger.warning(
            "Failed to cleanup sandbox worktree for chat %s: %s", chat_id[:8], exc
        )
        return False


async def _git_identity(repo_dir: str) -> list[str]:
    """Return ``-c user.name/-c user.email`` overrides for a bare repo.

    Fresh ``git init``/``git clone`` repos often have no user identity
    configured, which makes ``git commit`` fail with "Please tell me who you
    are".  Only inject overrides when the repo (local + global config) has no
    email, so configured environments keep their real author.
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "config", "--get", "user.email"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=5,
            env=_GIT_ENV,
        )
        if result.returncode == 0 and result.stdout.strip():
            return []
    except Exception:
        return []
    return [
        "-c",
        "user.name=Myrm Agent",
        "-c",
        "user.email=agent@myrm.local",
    ]


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

        await asyncio.to_thread(
            subprocess.run,
            ["git", "add", "-A"],
            cwd=worktree_path,
            capture_output=True,
            timeout=10,
            env=_GIT_ENV,
        )
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


async def merge_sandbox_to_parent(base_dir: str, chat_id: str) -> tuple[bool, str]:
    """Merge sandbox branch changes back to the parent branch.

    Returns (success, message) tuple.  Merges on the same base_dir are
    serialized with kanban merges so git's shared index is never written
    concurrently.
    """
    async with _get_merge_lock(base_dir):
        return await _merge_sandbox_to_parent_locked(base_dir, chat_id)


async def _merge_sandbox_to_parent_locked(
    base_dir: str, chat_id: str
) -> tuple[bool, str]:
    branch_name = f"sandbox/chat-{chat_id[:12]}"

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
                "Cannot commit dirty sandbox worktree %s for chat %s; "
                "merge skipped, worktree preserved",
                worktree_path,
                chat_id[:8],
            )
            return False, "Sandbox has uncommitted changes that could not be committed"

    try:
        identity = await _git_identity(base_dir)
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "git",
                *identity,
                "merge",
                "--no-ff",
                branch_name,
                "-m",
                f"Merge sandbox session {chat_id[:8]}",
            ],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=60,
            env=_GIT_ENV,
        )
        if result.returncode == 0:
            await cleanup_sandbox_worktree(base_dir, chat_id, force=True)
            return True, f"Successfully merged sandbox to {parent_branch}"
        # Roll the merge back so base_dir stays usable instead of lingering in
        # a mid-merge state that blocks every later merge on the same repo.
        conflicts = await _collect_conflict_files(base_dir)
        await _abort_merge(base_dir)
        message = "Merge conflict"
        if conflicts:
            message += f" in {len(conflicts)} file(s): {', '.join(conflicts[:5])}"
        return False, message
    except Exception:
        await _abort_merge(base_dir)
        return False, "Merge failed"


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
    """Roll back an in-progress merge so base_dir stays usable."""
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["git", "merge", "--abort"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=15,
            env=_GIT_ENV,
        )
    except Exception:
        pass
