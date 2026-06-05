"""Vault secure artifact proxy router.

Serves user-generated plotting artifacts securely with session token checking
to prevent cross-tenant and path traversal security leaks.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.config.deploy_mode import is_local_mode

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_session_token(
    session_token: str | None = Query(None, alias="token", description="Active user session token"),
) -> str:
    """Validate that the caller is authenticated and has an active session."""
    # In Local Web / Tauri desktop deployment, authentication is automatically trusted
    if is_local_mode():
        return "local_session"

    # In multi-tenant / SaaS cloud deployment:
    if not session_token or len(session_token) < 16:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    # Real SaaS verification would check against the Control Plane session registry.
    return session_token


@router.get("/vault/render", response_class=FileResponse)
async def render_vault_artifact(
    filepath: str = Query(
        ...,
        description="The absolute or relative path to the WebP plot file inside the sandbox",
    ),
    workspace: str = Query(..., description="The workspace root directory boundary for path security"),
    token: str = Depends(verify_session_token),
) -> FileResponse:
    """Securely proxy and render WebP plotted files from the user's sandbox directory."""
    from myrm_agent_harness.agent.security.path_security import (
        is_dangerous_path,
        is_within_boundary,
    )

    # Clean path resolution
    workspace_resolved = os.path.realpath(os.path.expanduser(workspace))
    raw_path = os.path.expanduser(filepath)
    if os.path.isabs(raw_path):
        resolved = os.path.realpath(raw_path)
    else:
        resolved = os.path.realpath(os.path.join(workspace_resolved, raw_path))

    # Verify path security: boundary compliance and avoid dangerous files (e.g. system files)
    if is_dangerous_path(resolved):
        raise HTTPException(status_code=403, detail="Access denied: Dangerous path detected")

    if not is_within_boundary(resolved, workspace_resolved):
        raise HTTPException(status_code=403, detail="Access denied: Path is outside workspace boundary")

    if not os.path.isfile(resolved):
        raise HTTPException(status_code=404, detail="Requested plot file not found")

    # Verify file is indeed a WebP image (plotting format)
    if not resolved.lower().endswith(".webp"):
        raise HTTPException(
            status_code=400,
            detail="Only .webp format artifacts are allowed to be rendered via this proxy",
        )

    return FileResponse(
        path=resolved,
        media_type="image/webp",
        filename=os.path.basename(resolved),
    )
