"""Local file actions API — reveal in file manager / open with default app.

Only available in local deployment mode (Tauri / WebUI).
SaaS/Sandbox mode returns 403 Forbidden.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: Deployment mode check)
- app.core.storage::files_service (POS: File service for metadata lookup)
- app.core.artifacts.listener::resolve_sandbox_file_path (POS: Locates a generated file inside its workspace)
- app.database.connection::get_db (POS: 获取数据库会话依赖注入)
- app.database.models.artifact::Artifact (POS: Provides enterprise artifact models with tamper-evident tracking)
- app.services.chat.effective_workspace::resolve_chat_workspace_root (POS: Workspace a chat's runs wrote to)

[OUTPUT]
- POST /files/{file_id}/reveal — Open the file's parent directory in the system file manager
- POST /files/{file_id}/open — Open the file with the system's default application
- POST /files/chats/{chat_id}/reveal — Open the workspace directory holding a chat session's artifacts

[POS]
Local-only file action endpoints. Enables desktop-class UX for artifact files:
reveal in Finder/Explorer and open with default app. Security: restricted to
local mode; a chat's files must sit inside that chat's workspace, every other file inside the state directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.artifacts.listener import resolve_sandbox_file_path
from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.services.chat.effective_workspace import resolve_chat_workspace_root
from app.services.files.reveal_utils import open_with_default_app, reveal_path_in_file_manager

router = APIRouter()


class ChatArtifactsRevealResponse(BaseModel):
    status: str
    path: str | None = None
    artifact_count: int = 0


def _get_workspace_dir() -> str:
    from app.config.settings import settings

    return settings.database.state_dir


def _validate_local_mode() -> None:
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="File actions only available in local mode")


async def _resolve_artifact_path(file_id: str) -> Path:
    """Resolve and validate the local filesystem path for a file ID."""
    from app.core.storage import FilesService

    svc = FilesService()
    file_obj = await svc.get_file(file_id)
    if file_obj is None:
        raise HTTPException(status_code=404, detail="File not found")

    storage_path = file_obj.storage_path
    if not storage_path:
        raise HTTPException(status_code=404, detail="File has no local path")

    chat_id = file_obj.source_chat_id
    chat_prefix = f"sandboxes/{chat_id}/"
    if chat_id and storage_path.startswith(chat_prefix):
        # A generated file lives in the workspace of the chat that produced it; the stored path is relative to it.
        base = (await resolve_chat_workspace_root(chat_id)).resolve()
        relative = storage_path.removeprefix(chat_prefix)
        resolved = base / relative
        if not resolved.exists() and (located := resolve_sandbox_file_path(relative, str(base), chat_id)):
            resolved = Path(located)
    else:
        base = Path(_get_workspace_dir()).resolve()
        resolved = Path(storage_path) if os.path.isabs(storage_path) else base / storage_path

    resolved = resolved.resolve()
    if not resolved.is_relative_to(base):
        raise HTTPException(status_code=403, detail="Path outside workspace directory")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File does not exist on disk")

    return resolved


@router.post("/{file_id}/reveal", tags=["files-local-actions"])
async def reveal_file(file_id: str) -> dict[str, str]:
    """Reveal a file in the system file manager (Finder/Explorer).

    Local mode only. Opens the parent directory with the file selected.
    """
    _validate_local_mode()
    path = await _resolve_artifact_path(file_id)
    reveal_path_in_file_manager(path)
    return {"status": "ok", "path": str(path)}


@router.post("/{file_id}/open", tags=["files-local-actions"])
async def open_file(file_id: str) -> dict[str, str]:
    """Open a file with the system's default application.

    Local mode only. Opens the file using the OS-registered handler
    (e.g. Excel for .xlsx, Preview for .png).
    """
    _validate_local_mode()
    path = await _resolve_artifact_path(file_id)
    open_with_default_app(path)
    return {"status": "ok", "path": str(path)}


async def _resolve_chat_artifacts_path(chat_id: str, db: AsyncSession) -> tuple[str, Path | None, int]:
    """Resolve the workspace directory holding the artifacts of a chat session.

    Returns:
        tuple[status, resolved_path, artifact_count]
            status: "ok" | "no_artifacts" | "missing_on_disk"
    """
    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.chat_id == chat_id, Artifact.is_deleted.is_(False))
    )
    artifacts = [artifact for artifact in (await db.execute(stmt)).scalars().all() if artifact.versions]
    if not artifacts:
        return "no_artifacts", None, 0

    workspace = (await resolve_chat_workspace_root(chat_id)).resolve()
    vault = ArtifactVault(str(workspace))
    on_disk = any(
        vault.get_object_path(latest.vault_uri.removeprefix(VAULT_PREFIX)).exists()
        for latest in (max(artifact.versions, key=lambda v: v.created_at) for artifact in artifacts)
        if latest.vault_uri
    )
    if not on_disk or not workspace.is_dir():
        return "missing_on_disk", None, len(artifacts)
    return "ok", workspace, len(artifacts)


@router.post(
    "/chats/{chat_id}/reveal",
    response_model=ChatArtifactsRevealResponse,
    tags=["files-local-actions"],
)
async def reveal_chat_artifacts(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> ChatArtifactsRevealResponse:
    """Reveal the workspace directory holding a chat session's artifacts in the system file manager.

    Local mode only.
    """
    _validate_local_mode()
    status, path, count = await _resolve_chat_artifacts_path(chat_id, db)
    if status == "ok" and path is not None:
        reveal_path_in_file_manager(path)
        return ChatArtifactsRevealResponse(status="ok", path=str(path), artifact_count=count)
    if status == "no_artifacts":
        return ChatArtifactsRevealResponse(status="no_artifacts", path=None, artifact_count=0)
    return ChatArtifactsRevealResponse(status="missing_on_disk", path=None, artifact_count=count)
