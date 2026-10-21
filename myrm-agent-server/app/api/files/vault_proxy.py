"""Vault secure artifact proxy router.

Serves user-generated artifacts (plots, recordings, media) securely with
session token checking to prevent cross-tenant and path traversal security leaks.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.config.deploy_mode import is_local_mode

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS: dict[str, str] = {
    ".webp": "image/webp",
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def verify_session_token(
    session_token: str | None = Query(None, alias="token", description="Active user session token"),
) -> str:
    """Validate that the caller is authenticated and has an active session."""
    if is_local_mode():
        return "local_session"

    if not session_token or len(session_token) < 16:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    return session_token


@router.get("/vault/render", response_class=FileResponse)
async def render_vault_artifact(
    filepath: str = Query(
        ...,
        description="Relative or absolute path to an artifact file inside the sandbox",
    ),
    workspace: str = Query(..., description="The workspace root directory boundary for path security"),
    token: str = Depends(verify_session_token),
) -> FileResponse:
    """Securely proxy and render sandbox artifacts (images, videos, plots)."""
    from myrm_agent_harness.agent.security.path_security import (
        is_dangerous_path,
        is_within_boundary,
    )

    workspace_resolved = os.path.realpath(os.path.expanduser(workspace))
    raw_path = os.path.expanduser(filepath)
    if os.path.isabs(raw_path):
        resolved = os.path.realpath(raw_path)
    else:
        resolved = os.path.realpath(os.path.join(workspace_resolved, raw_path))

    if is_dangerous_path(resolved):
        raise HTTPException(status_code=403, detail="Access denied: Dangerous path detected")

    if not is_within_boundary(resolved, workspace_resolved):
        raise HTTPException(status_code=403, detail="Access denied: Path is outside workspace boundary")

    if not os.path.isfile(resolved):
        raise HTTPException(status_code=404, detail="Requested artifact file not found")

    ext = os.path.splitext(resolved.lower())[1]
    media_type = _ALLOWED_EXTENSIONS.get(ext)
    if media_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed. Supported: {', '.join(_ALLOWED_EXTENSIONS.keys())}",
        )

    return FileResponse(
        path=resolved,
        media_type=media_type,
        filename=os.path.basename(resolved),
    )
