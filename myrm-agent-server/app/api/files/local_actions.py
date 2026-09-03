"""Local file actions API — reveal in file manager / open with default app.

Only available in local deployment mode (Tauri / WebUI).
SaaS/Sandbox mode returns 403 Forbidden.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: Deployment mode check)
- app.core.storage::files_service (POS: File service for metadata lookup)
- app.database.connection::get_db (POS: 获取数据库会话依赖注入)
- app.database.models.artifact::Artifact (POS: Provides enterprise artifact models with tamper-evident tracking)

[OUTPUT]
- POST /files/{file_id}/reveal — Open the file's parent directory in the system file manager
- POST /files/{file_id}/open — Open the file with the system's default application
- POST /files/chats/{chat_id}/reveal — Open the artifacts directory for a given chat session

[POS]
Local-only file action endpoints. Enables desktop-class UX for artifact files:
reveal in Finder/Explorer and open with default app. Security: restricted to
local mode and workspace directory.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.services.files.reveal_utils import open_with_default_app, reveal_path_in_file_manager

router = APIRouter()
logger = logging.getLogger(__name__)


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

    workspace_dir = _get_workspace_dir()

    if storage_path.startswith("sandboxes/"):
        parts = storage_path.split("/", 2)
        if len(parts) >= 3:
            relative = parts[2]
            resolved = Path(workspace_dir) / relative
        else:
            raise HTTPException(status_code=404, detail="Invalid storage path format")
    elif os.path.isabs(storage_path):
        resolved = Path(storage_path)
    else:
        resolved = Path(workspace_dir) / storage_path

    resolved = resolved.resolve()

    workspace_resolved = Path(workspace_dir).resolve()
    if not resolved.is_relative_to(workspace_resolved):
        raise HTTPException(status_code=403, detail="Path outside workspace directory")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File does not exist on disk")

    return resolved


@router.post("/files/{file_id}/reveal", tags=["files-local-actions"])
async def reveal_file(file_id: str) -> dict[str, str]:
    """Reveal a file in the system file manager (Finder/Explorer).

    Local mode only. Opens the parent directory with the file selected.
    """
    _validate_local_mode()
    path = await _resolve_artifact_path(file_id)
    reveal_path_in_file_manager(path)
    return {"status": "ok", "path": str(path)}


@router.post("/files/{file_id}/open", tags=["files-local-actions"])
async def open_file(file_id: str) -> dict[str, str]:
    """Open a file with the system's default application.

    Local mode only. Opens the file using the OS-registered handler
    (e.g. Excel for .xlsx, Preview for .png).
    """
    _validate_local_mode()
    path = await _resolve_artifact_path(file_id)
    open_with_default_app(path)
    return {"status": "ok", "path": str(path)}


async def _resolve_chat_artifacts_path(
    chat_id: str,
    db: AsyncSession | None = None,
) -> tuple[str, Path | None, int]:
    """Resolve the filesystem directory containing artifacts for a given chat session.

    Returns:
        tuple[status, resolved_path, artifact_count]
            status: "ok" | "no_artifacts" | "missing_on_disk"
    """
    workspace_dir = _get_workspace_dir()
    workspace_resolved = Path(workspace_dir).resolve()

    candidate_files: list[Path] = []
    total_recorded = 0

    # 1. Check physical sandbox directory
    sandbox_dir = (workspace_resolved / "sandboxes" / chat_id).resolve()
    if sandbox_dir.exists() and sandbox_dir.is_dir():
        for item in sandbox_dir.rglob("*"):
            if item.is_file():
                candidate_files.append(item)
                total_recorded += 1

    # 2. Check Artifact records associated with this chat_id
    if db is not None:
        try:
            stmt = (
                select(Artifact)
                .options(selectinload(Artifact.versions))
                .where(Artifact.chat_id == chat_id, Artifact.is_deleted.is_(False))
            )
            result = await db.execute(stmt)
            artifacts = result.scalars().all()
            for art in artifacts:
                if not art.versions:
                    continue
                total_recorded += 1
                latest = max(art.versions, key=lambda v: v.created_at)
                if latest.vault_uri:
                    uri = latest.vault_uri
                    obj_id = uri[len("vault://") :] if uri.startswith("vault://") else uri
                    from myrm_agent_harness.core.artifacts.paths import resolve_workspace_artifact_vault_dir

                    vault_path = resolve_workspace_artifact_vault_dir(workspace_resolved) / "objects" / obj_id
                    if vault_path.exists():
                        candidate_files.append(vault_path)
        except Exception as e:
            logger.warning(f"Error querying artifacts for chat {chat_id}: {e}")

    # 3. Handle cases where no artifacts are recorded
    if total_recorded == 0 and not candidate_files:
        return "no_artifacts", None, 0

    if total_recorded > 0 and not candidate_files:
        return "missing_on_disk", None, total_recorded

    # 4. Resolve the target directory
    if sandbox_dir.exists() and any(p.is_relative_to(sandbox_dir) for p in candidate_files):
        target_dir = sandbox_dir
    elif len(candidate_files) == 1:
        target_dir = candidate_files[0].parent
    else:
        try:
            common = os.path.commonpath([str(p.parent) for p in candidate_files])
            target_dir = Path(common)
            if target_dir.resolve() == workspace_resolved:
                target_dir = candidate_files[0].parent
        except ValueError:
            target_dir = candidate_files[0].parent

    target_resolved = target_dir.resolve()
    if not target_resolved.is_relative_to(workspace_resolved):
        raise HTTPException(status_code=403, detail="Path outside workspace directory")

    if not target_resolved.exists():
        return "missing_on_disk", None, total_recorded

    return "ok", target_resolved, total_recorded


@router.post(
    "/files/chats/{chat_id}/reveal",
    response_model=ChatArtifactsRevealResponse,
    tags=["files-local-actions"],
)
async def reveal_chat_artifacts(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> ChatArtifactsRevealResponse:
    """Reveal the artifacts directory for a given chat session in the system file manager.

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
