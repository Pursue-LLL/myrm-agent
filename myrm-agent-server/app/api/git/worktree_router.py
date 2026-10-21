"""FastAPI router for Git Worktree management and session checkout anchoring.

[INPUT]
- FastAPI endpoints for worktree listing, creation, switching, removal, and session checkout anchoring.
- Pydantic models for request payloads.

[OUTPUT]
- router: APIRouter instance mounted under `/api/git` (or `/git`)

[POS]
app/api/git/worktree_router.py: 提供 Git 多工作树与会话锚定 API，
由 app/api/router.py 挂载并在前端 useWorktreeStore / GitWorktreeDropdown 中消费。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.git.worktree_service import (
    GitWorktreeInfo,
    GitWorktreeService,
    SessionCheckoutAnchorInfo,
    SessionTouchedFileInfo,
    get_worktree_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/git", tags=["Git Worktrees"])


class CreateWorktreeRequest(BaseModel):
    branch: str = Field(..., min_length=1, description="Branch name to check out in new worktree")
    repo_path: str | None = Field(default=None, description="Optional target repo path; defaults to workspace root")
    worktree_path: str | None = Field(default=None, description="Optional custom directory path")
    base_ref: str | None = Field(default="HEAD", description="Base commit or branch to branch off from")


class SwitchWorktreeRequest(BaseModel):
    worktree_path: str = Field(..., min_length=1, description="Path of target worktree to activate")
    repo_path: str | None = Field(default=None, description="Optional repo root path")


class BindCheckoutAnchorRequest(BaseModel):
    checkout_ref: str = Field(..., description="Commit hash or branch name at session creation")
    worktree_path: str = Field(..., description="Absolute worktree directory path")
    repo_path: str | None = Field(default=None, description="Optional repo root path")
    touched_files: list[SessionTouchedFileInfo] = Field(default_factory=list, description="Files touched by session")


class RemoveWorktreeResponse(BaseModel):
    removed: bool
    path: str


@router.get(
    "/worktrees",
    response_model=list[GitWorktreeInfo],
    summary="List all git worktrees in project repository",
)
async def list_worktrees(
    repo_path: Annotated[str | None, Query(description="Repository path")] = None,
    service: GitWorktreeService = Depends(get_worktree_service),
) -> list[GitWorktreeInfo]:
    """List all worktrees in the repository with branch, commit, dirty, and active status."""
    return await service.list_worktrees(repo_path=repo_path)


@router.post(
    "/worktrees",
    response_model=GitWorktreeInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new isolated git worktree",
)
async def create_worktree(
    body: CreateWorktreeRequest,
    service: GitWorktreeService = Depends(get_worktree_service),
) -> GitWorktreeInfo:
    """Create a new git worktree and branch off from base ref."""
    try:
        return await service.create_worktree(
            branch=body.branch,
            repo_path=body.repo_path,
            worktree_path=body.worktree_path,
            base_ref=body.base_ref,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to create worktree: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Worktree creation error: {exc}",
        ) from exc


@router.post(
    "/worktrees/switch",
    response_model=GitWorktreeInfo,
    summary="Switch active worktree pointer",
)
async def switch_worktree(
    body: SwitchWorktreeRequest,
    service: GitWorktreeService = Depends(get_worktree_service),
) -> GitWorktreeInfo:
    """Switch active worktree in the workspace context."""
    try:
        return await service.switch_worktree(
            worktree_path=body.worktree_path,
            repo_path=body.repo_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to switch worktree: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Worktree switch error: {exc}",
        ) from exc


@router.delete(
    "/worktrees",
    response_model=RemoveWorktreeResponse,
    summary="Remove a git worktree",
)
async def remove_worktree(
    worktree_path: Annotated[str, Query(description="Absolute path to worktree to remove")],
    repo_path: Annotated[str | None, Query(description="Optional repo path")] = None,
    force: Annotated[bool, Query(description="Force remove even if dirty")] = False,
    service: GitWorktreeService = Depends(get_worktree_service),
) -> RemoveWorktreeResponse:
    """Remove an existing worktree directory."""
    try:
        ok = await service.remove_worktree(
            worktree_path=worktree_path,
            repo_path=repo_path,
            force=force,
        )
        return RemoveWorktreeResponse(removed=ok, path=worktree_path)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to remove worktree: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Worktree remove error: {exc}",
        ) from exc


@router.get(
    "/sessions/{session_id}/checkout-anchor",
    response_model=SessionCheckoutAnchorInfo,
    summary="Get session checkout anchoring metadata and touched files",
)
def get_session_checkout_anchor(
    session_id: str,
    repo_path: Annotated[str | None, Query(description="Repository path")] = None,
    service: GitWorktreeService = Depends(get_worktree_service),
) -> SessionCheckoutAnchorInfo:
    """Retrieve session checkout ref, worktree path, anchor status, and touched files."""
    return service.get_session_checkout_anchor(session_id=session_id, repo_path=repo_path)


@router.post(
    "/sessions/{session_id}/checkout-anchor",
    response_model=SessionCheckoutAnchorInfo,
    summary="Bind or update session checkout anchor",
)
def bind_session_checkout_anchor(
    session_id: str,
    body: BindCheckoutAnchorRequest,
    service: GitWorktreeService = Depends(get_worktree_service),
) -> SessionCheckoutAnchorInfo:
    """Bind a session to a specific checkout ref and worktree directory with touched files."""
    return service.bind_session_checkout_anchor(
        session_id=session_id,
        checkout_ref=body.checkout_ref,
        worktree_path=body.worktree_path,
        repo_path=body.repo_path,
        touched_files=body.touched_files,
    )
