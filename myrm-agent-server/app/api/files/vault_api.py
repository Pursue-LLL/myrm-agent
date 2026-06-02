import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault

from app.api.dependencies import get_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{obj_id}/content")
async def get_vault_object_content(
    obj_id: str,
    download: int = 0,
    workspace_root: Path = Depends(get_workspace_root),
) -> Response:
    """Retrieve the raw binary/text content of a vault object.
    
    This is the non-blocking GET endpoint used by the frontend to asynchronously 
    download massive artifacts (pointers like vault://uuid) without 
    clogging the SSE stream.
    """
    try:
        vault = ArtifactVault(str(workspace_root))
        uri = f"{VAULT_PREFIX}{obj_id}"
        
        meta = vault.get_meta(uri)
        if not meta:
            raise HTTPException(status_code=404, detail="Vault object metadata not found or expired")
            
        obj_path = vault.get_object_path(obj_id)
        if not obj_path.exists():
            raise HTTPException(status_code=404, detail="Vault object content not found on disk")
        
        disposition = "attachment" if download == 1 else "inline"
        
        return FileResponse(
            path=str(obj_path),
            media_type=meta.content_type,
            filename=meta.filename,
            content_disposition_type=disposition
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve vault object {obj_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{obj_id}/meta")
async def get_vault_object_meta(
    obj_id: str,
    workspace_root: Path = Depends(get_workspace_root),
) -> dict[str, object]:
    """Retrieve the metadata (size, filename, type) of a vault object."""
    try:
        vault = ArtifactVault(str(workspace_root))
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
        raise HTTPException(status_code=500, detail=str(e)) from e
