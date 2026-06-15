"""[INPUT]
- app.services.chat.sandbox_worktree (POS: Shared worktree lifecycle management)
- app.services.chat.chat_service::ChatService (POS: Chat metadata persistence)

[OUTPUT]
- POST /{chat_id}/sandbox/enable: Activate sandbox mode for a chat session.
- POST /{chat_id}/sandbox/disable: Deactivate sandbox (discard changes).
- POST /{chat_id}/sandbox/merge: Merge sandbox changes back to parent branch.
- GET /{chat_id}/sandbox/status: Query sandbox state for a chat.
- GET /{chat_id}/sandbox/diff: Retrieve unified diff of all sandbox changes.

[POS]
API endpoints for managing chat sandbox sessions (git worktree isolation).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import weakref
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.utils.response_utils import success_response
from app.services.chat.chat_service import ChatService
from app.services.chat.sandbox_worktree import (
    cleanup_sandbox_worktree,
    create_sandbox_worktree,
    get_sandbox_worktree_path,
    is_git_repository,
    merge_sandbox_to_parent,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_sandbox_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _get_sandbox_lock(chat_id: str) -> asyncio.Lock:
    lock = _sandbox_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _sandbox_locks[chat_id] = lock
    return lock


class SandboxStatusResponse(BaseModel):
    active: bool
    worktree_path: str | None = None
    branch: str | None = None
    base_dir: str | None = None


class SandboxMergeResponse(BaseModel):
    success: bool
    message: str


async def _resolve_chat_base_dir(chat_id: str) -> tuple[str | None, str | None]:
    """Resolve the base workspace directory and sandbox_base_dir for a chat.

    Returns (effective_base_dir, sandbox_base_dir).
    If sandbox is active, sandbox_base_dir holds the original repo root.
    """
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        return None, None

    sandbox_base = chat.sandbox_base_dir

    if chat.project_id:
        from app.services.project.project_service import ProjectService

        project = await ProjectService.get_project(chat.project_id)
        if project and project.workspace_path:
            return project.workspace_path, sandbox_base

    return chat.workspace_dir, sandbox_base


@router.post("/{chat_id}/sandbox/enable")
async def enable_sandbox(chat_id: str):
    """Activate sandbox mode for a chat session.

    Creates an isolated git worktree so the agent can freely
    experiment without affecting the main branch.
    """
    async with _get_sandbox_lock(chat_id):
        effective_dir, existing_sandbox_base = await _resolve_chat_base_dir(chat_id)
        if not effective_dir:
            raise HTTPException(status_code=400, detail="Chat has no associated workspace directory")

        base_dir = existing_sandbox_base or effective_dir

        if not await is_git_repository(base_dir):
            raise HTTPException(status_code=400, detail="Workspace is not a git repository")

        worktree_path = await create_sandbox_worktree(base_dir, chat_id)
        if not worktree_path:
            raise HTTPException(status_code=500, detail="Failed to create sandbox worktree")

        await ChatService.update_chat_fields(chat_id, {
            "workspace_dir": worktree_path,
            "sandbox_base_dir": base_dir,
        })

        return success_response({
            "active": True,
            "worktree_path": worktree_path,
            "branch": f"sandbox/chat-{chat_id[:12]}",
            "base_dir": base_dir,
        })


@router.post("/{chat_id}/sandbox/disable")
async def disable_sandbox(chat_id: str):
    """Deactivate sandbox mode and discard all changes."""
    async with _get_sandbox_lock(chat_id):
        _, sandbox_base = await _resolve_chat_base_dir(chat_id)
        if not sandbox_base:
            raise HTTPException(status_code=400, detail="No active sandbox session")

        success = await cleanup_sandbox_worktree(sandbox_base, chat_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to cleanup sandbox worktree")

        await ChatService.update_chat_fields(chat_id, {
            "workspace_dir": sandbox_base,
            "sandbox_base_dir": None,
        })

        return success_response({"active": False, "message": "Sandbox discarded"})


@router.post("/{chat_id}/sandbox/merge")
async def merge_sandbox(chat_id: str):
    """Merge sandbox branch changes back to the parent branch."""
    async with _get_sandbox_lock(chat_id):
        _, sandbox_base = await _resolve_chat_base_dir(chat_id)
        if not sandbox_base:
            raise HTTPException(status_code=400, detail="No active sandbox session")

        success, message = await merge_sandbox_to_parent(sandbox_base, chat_id)

        if success:
            await ChatService.update_chat_fields(chat_id, {
                "workspace_dir": sandbox_base,
                "sandbox_base_dir": None,
            })

        return success_response(SandboxMergeResponse(success=success, message=message).model_dump())


@router.get("/{chat_id}/sandbox/status")
async def sandbox_status(chat_id: str):
    """Query the sandbox state for a chat session."""
    _, sandbox_base = await _resolve_chat_base_dir(chat_id)

    if not sandbox_base:
        return success_response(SandboxStatusResponse(active=False).model_dump())

    sandbox_path = get_sandbox_worktree_path(sandbox_base, chat_id)
    active = Path(sandbox_path).exists()

    return success_response(SandboxStatusResponse(
        active=active,
        worktree_path=sandbox_path if active else None,
        branch=f"sandbox/chat-{chat_id[:12]}" if active else None,
        base_dir=sandbox_base,
    ).model_dump())


@router.get("/{chat_id}/sandbox/diff")
async def sandbox_diff(chat_id: str):
    """Retrieve the unified diff of all sandbox changes vs. the parent branch."""
    _, sandbox_base = await _resolve_chat_base_dir(chat_id)
    if not sandbox_base:
        raise HTTPException(status_code=400, detail="No active sandbox session")

    sandbox_path = get_sandbox_worktree_path(sandbox_base, chat_id)
    if not Path(sandbox_path).exists():
        raise HTTPException(status_code=400, detail="Sandbox worktree not found")

    try:
        stat_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "diff", "--stat", "HEAD"],
            cwd=sandbox_path,
            capture_output=True,
            text=True,
            timeout=15,
        )

        diff_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "diff", "HEAD"],
            cwd=sandbox_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if diff_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git diff failed: {diff_result.stderr.strip()}")

        return success_response({
            "stat": stat_result.stdout if stat_result.returncode == 0 else "",
            "diff": diff_result.stdout,
            "has_changes": bool(diff_result.stdout.strip()),
        })
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="git diff timed out")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Failed to get sandbox diff for chat %s: %s", chat_id[:8], exc)
        raise HTTPException(status_code=500, detail=f"Failed to get diff: {exc}")
