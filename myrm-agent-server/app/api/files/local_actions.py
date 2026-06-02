"""Local file actions API — reveal in file manager / open with default app.

Only available in local deployment mode (Tauri / WebUI).
SaaS/Sandbox mode returns 403 Forbidden.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: Deployment mode check)
- app.core.storage::files_service (POS: File service for metadata lookup)

[OUTPUT]
- POST /files/{file_id}/reveal — Open the file's parent directory in the system file manager
- POST /files/{file_id}/open — Open the file with the system's default application

[POS]
Local-only file action endpoints. Enables desktop-class UX for artifact files:
reveal in Finder/Explorer and open with default app. Security: restricted to
local mode and workspace directory.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)


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


def _reveal_in_file_manager(path: Path) -> None:
    """Open the file's parent directory in the system file manager."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
        elif system == "Windows":
            subprocess.Popen(["explorer.exe", f"/select,{path}"])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"File manager command not found on {system}") from None


def _open_with_default_app(path: Path) -> None:
    """Open the file with the system's default application."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Open command not found on {system}") from None


@router.post("/files/{file_id}/reveal", tags=["files-local-actions"])
async def reveal_file(file_id: str) -> dict[str, str]:
    """Reveal a file in the system file manager (Finder/Explorer).

    Local mode only. Opens the parent directory with the file selected.
    """
    _validate_local_mode()
    path = await _resolve_artifact_path(file_id)
    _reveal_in_file_manager(path)
    return {"status": "ok", "path": str(path)}


@router.post("/files/{file_id}/open", tags=["files-local-actions"])
async def open_file(file_id: str) -> dict[str, str]:
    """Open a file with the system's default application.

    Local mode only. Opens the file using the OS-registered handler
    (e.g. Excel for .xlsx, Preview for .png).
    """
    _validate_local_mode()
    path = await _resolve_artifact_path(file_id)
    _open_with_default_app(path)
    return {"status": "ok", "path": str(path)}
