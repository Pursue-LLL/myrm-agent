"""[INPUT]
- app.services.chat.sandbox_worktree (POS: Shared worktree lifecycle management)
- app.services.chat.chat_service::ChatService (POS: Chat metadata persistence)

[OUTPUT]
- POST /{chat_id}/sandbox/enable: Activate sandbox mode for a chat session.
- POST /{chat_id}/sandbox/disable: Deactivate sandbox (discard changes).
- POST /{chat_id}/sandbox/merge: Merge sandbox changes back to parent branch.
- GET /{chat_id}/sandbox/status: Query sandbox state for a chat.

[POS]
API endpoints for managing chat sandbox sessions (git worktree isolation).
"""

from __future__ import annotations

import logging
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


class SandboxStatusResponse(BaseModel):
    active: bool
    worktree_path: str | None = None
    branch: str | None = None
    base_dir: str | None = None


class SandboxMergeResponse(BaseModel):
    success: bool
    message: str


async def _resolve_chat_base_dir(chat_id: str) -> str | None:
    """Resolve the base workspace directory for a chat session."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        return None

    if chat.project_id:
        from app.services.project.project_service import ProjectService

        project = await ProjectService.get_project(chat.project_id)
        if project and project.workspace_path:
            return project.workspace_path

    return chat.workspace_dir


@router.post("/{chat_id}/sandbox/enable")
async def enable_sandbox(chat_id: str):
    """Activate sandbox mode for a chat session.

    Creates an isolated git worktree so the agent can freely
    experiment without affecting the main branch.
    """
    base_dir = await _resolve_chat_base_dir(chat_id)
    if not base_dir:
        raise HTTPException(status_code=400, detail="Chat has no associated workspace directory")

    if not await is_git_repository(base_dir):
        raise HTTPException(status_code=400, detail="Workspace is not a git repository")

    worktree_path = await create_sandbox_worktree(base_dir, chat_id)
    if not worktree_path:
        raise HTTPException(status_code=500, detail="Failed to create sandbox worktree")

    await ChatService.update_chat_fields(chat_id, {
        "workspace_dir": worktree_path,
    })

    return success_response({
        "active": True,
        "worktree_path": worktree_path,
        "branch": f"sandbox/chat-{chat_id[:12]}",
    })


@router.post("/{chat_id}/sandbox/disable")
async def disable_sandbox(chat_id: str):
    """Deactivate sandbox mode and discard all changes."""
    base_dir = await _resolve_chat_base_dir(chat_id)
    if not base_dir:
        raise HTTPException(status_code=400, detail="Chat has no associated workspace directory")

    parent_dir = base_dir
    sandbox_path = get_sandbox_worktree_path(base_dir, chat_id)
    if Path(sandbox_path).exists():
        parent_dir = base_dir
    elif base_dir.endswith(f"sandbox-{chat_id[:12]}"):
        parent_dir = str(Path(base_dir).parent.parent)

    success = await cleanup_sandbox_worktree(parent_dir, chat_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cleanup sandbox worktree")

    await ChatService.update_chat_fields(chat_id, {
        "workspace_dir": parent_dir,
    })

    return success_response({"active": False, "message": "Sandbox discarded"})


@router.post("/{chat_id}/sandbox/merge")
async def merge_sandbox(chat_id: str):
    """Merge sandbox branch changes back to the parent branch."""
    base_dir = await _resolve_chat_base_dir(chat_id)
    if not base_dir:
        raise HTTPException(status_code=400, detail="Chat has no associated workspace directory")

    parent_dir = base_dir
    if base_dir.endswith(f"sandbox-{chat_id[:12]}"):
        parent_dir = str(Path(base_dir).parent.parent)

    success, message = await merge_sandbox_to_parent(parent_dir, chat_id)

    if success:
        await ChatService.update_chat_fields(chat_id, {
            "workspace_dir": parent_dir,
        })

    return success_response(SandboxMergeResponse(success=success, message=message).model_dump())


@router.get("/{chat_id}/sandbox/status")
async def sandbox_status(chat_id: str):
    """Query the sandbox state for a chat session."""
    base_dir = await _resolve_chat_base_dir(chat_id)
    if not base_dir:
        return success_response(SandboxStatusResponse(active=False).model_dump())

    sandbox_path = get_sandbox_worktree_path(base_dir, chat_id)

    if Path(sandbox_path).exists():
        return success_response(SandboxStatusResponse(
            active=True,
            worktree_path=sandbox_path,
            branch=f"sandbox/chat-{chat_id[:12]}",
            base_dir=base_dir,
        ).model_dump())

    if base_dir.endswith(f"sandbox-{chat_id[:12]}"):
        return success_response(SandboxStatusResponse(
            active=True,
            worktree_path=base_dir,
            branch=f"sandbox/chat-{chat_id[:12]}",
            base_dir=str(Path(base_dir).parent.parent),
        ).model_dump())

    return success_response(SandboxStatusResponse(active=False).model_dump())
