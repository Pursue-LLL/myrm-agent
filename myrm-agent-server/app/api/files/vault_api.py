"""Vault object read API.

[INPUT]
- app.services.chat.effective_workspace::resolve_chat_workspace_root (POS: Workspace root a chat's runs wrote to)
- app.database.models.artifact::Artifact, ArtifactVersion (POS: Artifact → originating chat lookup)
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault (POS: Vault object store)

[OUTPUT]
- GET /{obj_id}/content — raw content of a vault object
- GET /{obj_id}/meta — metadata of a vault object

[POS]
A vault object lives in the workspace of the chat whose run wrote it. The caller names that chat with
``chat_id``; objects registered as artifacts are found through their artifact's chat; anything else is
looked up under the default workspace root.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_workspace_root
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.chat.effective_workspace import resolve_chat_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter()

_CHAT_ID_QUERY = Query(None, description="Chat whose run wrote the object; omit for objects registered as artifacts")


async def _artifact_chat_id(db: AsyncSession, obj_id: str) -> str | None:
    owner: str | None = await db.scalar(
        select(Artifact.chat_id)
        .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
        .where(ArtifactVersion.vault_uri == f"{VAULT_PREFIX}{obj_id}", Artifact.chat_id.is_not(None))
        .limit(1)
    )
    return owner


async def _open_vault(obj_id: str, chat_id: str | None, db: AsyncSession, default_root: Path) -> ArtifactVault:
    owner_chat_id = (chat_id or "").strip() or await _artifact_chat_id(db, obj_id)
    root = await resolve_chat_workspace_root(owner_chat_id) if owner_chat_id else default_root
    return ArtifactVault(str(root))


@router.get("/{obj_id}/content")
async def get_vault_object_content(
    obj_id: str,
    download: int = 0,
    chat_id: str | None = _CHAT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    workspace_root: Path = Depends(get_workspace_root),
) -> Response:
    """Retrieve the raw binary/text content of a vault object.

    This is the non-blocking GET endpoint used by the frontend to asynchronously
    download massive artifacts (pointers like vault://uuid) without
    clogging the SSE stream.
    """
    try:
        vault = await _open_vault(obj_id, chat_id, db, workspace_root)
        uri = f"{VAULT_PREFIX}{obj_id}"

        meta = vault.get_meta(uri)
        if not meta:
            raise HTTPException(status_code=404, detail="Vault object metadata not found or expired")

        obj_path = vault.get_object_path(obj_id)
        if not obj_path.exists():
            raise HTTPException(status_code=404, detail="Vault object content not found on disk")

        disposition = "attachment" if download == 1 else "inline"

        return FileResponse(
            path=str(obj_path), media_type=meta.content_type, filename=meta.filename, content_disposition_type=disposition
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve vault object {obj_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve vault object") from e


@router.get("/{obj_id}/meta")
async def get_vault_object_meta(
    obj_id: str,
    chat_id: str | None = _CHAT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    workspace_root: Path = Depends(get_workspace_root),
) -> dict[str, object]:
    """Retrieve the metadata (size, filename, type) of a vault object."""
    try:
        vault = await _open_vault(obj_id, chat_id, db, workspace_root)
        uri = f"{VAULT_PREFIX}{obj_id}"

        meta = vault.get_meta(uri)
        if not meta:
            raise HTTPException(status_code=404, detail="Vault object metadata not found")

        raw = meta.to_dict()
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items()}
        return {}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve vault object meta {obj_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve vault object metadata") from e
