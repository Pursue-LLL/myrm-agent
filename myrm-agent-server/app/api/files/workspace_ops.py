"""Workspace file write operations API.

Provides upload, mkdir, rename, move, delete and content-save for workspace
files.  All endpoints enforce a 6-layer security stack reusing the harness
path_security module: workspace boundary · dangerous-path block ·
sensitive-file guard · filename legality · delete protection · upload caps.

Read-only endpoints remain in browse.py — this module handles writes only.

[INPUT]
- myrm_agent_harness.core.security.path_security::is_within_boundary
- myrm_agent_harness.core.security.path_security::is_dangerous_path
- myrm_agent_harness.core.security.path_security::is_sensitive_file
- app.config.settings::settings.rate_limit.file_upload
- app.core.infra.limiter::limiter
- app.core.utils.errors::validation_error
- app.core.utils.response_utils::success_response

[OUTPUT]
- POST   /browse/upload   — Upload files into workspace directory
- POST   /browse/mkdir    — Create directory inside workspace
- POST   /browse/rename   — Rename file or directory
- POST   /browse/move     — Move file or directory
- DELETE /browse/delete   — Delete file or directory
- PUT    /browse/content  — Save file content (online edit)

[POS]
Workspace file write operations.  Separated from browse.py (read-only) for
single-responsibility and easier security auditing of write paths.
"""

import logging
import os
import re
import shutil

from fastapi import APIRouter, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB per file
_MAX_UPLOAD_COUNT = 20
_MAX_CONTENT_SAVE_SIZE = 5 * 1024 * 1024  # 5 MB for inline edit
_MAX_FILENAME_LEN = 255
_MAX_DELETE_ENTRIES = 500

_PROTECTED_NAMES: frozenset[str] = frozenset({".git"})
_ILLEGAL_NAME_RE = re.compile(r"[/\x00]")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class MkdirRequest(BaseModel):
    workspace: str = Field(..., description="Workspace root path")
    path: str = Field(..., description="New directory path (relative or absolute)")


class RenameRequest(BaseModel):
    workspace: str = Field(..., description="Workspace root path")
    path: str = Field(..., description="Current file/dir path")
    new_name: str = Field(
        ..., min_length=1, max_length=_MAX_FILENAME_LEN, description="New name (basename only, no path separators)"
    )


class MoveRequest(BaseModel):
    workspace: str = Field(..., description="Workspace root path")
    source: str = Field(..., description="Source file/dir path")
    target_dir: str = Field(..., description="Target directory path")


class SaveContentRequest(BaseModel):
    workspace: str = Field(..., description="Workspace root path")
    path: str = Field(..., description="File path to save")
    content: str = Field(..., description="New file content")


class UploadResult(BaseModel):
    name: str
    path: str
    size: int


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _resolve_workspace(workspace: str) -> str:
    """Resolve and validate workspace root."""
    from myrm_agent_harness.core.security.path_security import is_dangerous_path

    resolved = os.path.realpath(os.path.expanduser(workspace))
    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied for workspace: {workspace}")
    if not os.path.isdir(resolved):
        raise validation_error(f"Workspace is not a directory: {workspace}")
    return resolved


def _validate_target(target: str, workspace: str, *, allow_sensitive: bool = False) -> str:
    """Resolve target path and run boundary + danger + sensitive checks."""
    from myrm_agent_harness.core.security.path_security import (
        is_dangerous_path,
        is_sensitive_file,
        is_within_boundary,
    )

    resolved = os.path.realpath(os.path.expanduser(target))
    if not is_within_boundary(resolved, workspace):
        raise validation_error("Path is outside workspace boundary")
    if is_dangerous_path(resolved):
        raise validation_error("Access denied: dangerous path")
    if not allow_sensitive and is_sensitive_file(resolved):
        raise validation_error("Access denied: sensitive file")
    return resolved


def _validate_name(name: str) -> None:
    """Ensure a filename/dirname is legal."""
    if not name or not name.strip():
        raise validation_error("Name cannot be empty")
    if len(name) > _MAX_FILENAME_LEN:
        raise validation_error(f"Name exceeds {_MAX_FILENAME_LEN} characters")
    if _ILLEGAL_NAME_RE.search(name):
        raise validation_error("Name contains illegal characters")
    if name in (".", ".."):
        raise validation_error("Name cannot be '.' or '..'")


def _dedup_filename(directory: str, filename: str) -> str:
    """Return a unique filename by appending (1), (2), … if needed."""
    candidate = os.path.join(directory, filename)
    if not os.path.exists(candidate):
        return filename

    base, ext = os.path.splitext(filename)
    counter = 1
    while True:
        deduped = f"{base} ({counter}){ext}"
        if not os.path.exists(os.path.join(directory, deduped)):
            return deduped
        counter += 1
        if counter > 999:
            raise validation_error("Too many duplicate filenames")


def _count_entries(path: str) -> int:
    """Count files and directories recursively (capped)."""
    count = 0
    for _root, dirs, files in os.walk(path):
        count += len(dirs) + len(files)
        if count > _MAX_DELETE_ENTRIES:
            return count
    return count


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/browse/upload", response_model=None)
@limiter.limit(settings.rate_limit.file_upload)
async def upload_to_workspace(
    request: Request,
    workspace: str = Query(..., description="Workspace root path"),
    target_dir: str = Query("", description="Target directory (relative to workspace, empty = root)"),
    files: list[UploadFile] = Form(..., description="Files to upload"),
) -> JSONResponse:
    """Upload files into a workspace directory.

    Files are written directly to the filesystem inside the workspace boundary.
    Duplicate filenames are auto-suffixed (e.g. file.txt → file (1).txt).
    """
    if not files:
        raise validation_error("At least one file is required")
    if len(files) > _MAX_UPLOAD_COUNT:
        raise validation_error(f"Maximum {_MAX_UPLOAD_COUNT} files per upload")

    ws = _resolve_workspace(workspace)

    dest_dir = ws
    if target_dir and target_dir.strip():
        raw = os.path.join(ws, target_dir.strip().lstrip("/"))
        dest_dir = _validate_target(raw, ws, allow_sensitive=True)
        if not os.path.isdir(dest_dir):
            raise validation_error(f"Target directory does not exist: {target_dir}")

    results: list[UploadResult] = []
    for upload_file in files:
        if not upload_file.filename:
            continue
        _validate_name(upload_file.filename)

        content = await upload_file.read()
        if len(content) > _MAX_UPLOAD_SIZE:
            raise validation_error(f"File {upload_file.filename} exceeds {_MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit")

        safe_name = _dedup_filename(dest_dir, upload_file.filename)
        dest_path = os.path.join(dest_dir, safe_name)

        _validate_target(dest_path, ws, allow_sensitive=True)

        with open(dest_path, "wb") as f:
            f.write(content)

        results.append(
            UploadResult(
                name=safe_name,
                path=dest_path,
                size=len(content),
            )
        )

    return success_response(
        data={
            "uploaded_count": len(results),
            "files": [r.model_dump() for r in results],
        }
    )


@router.post("/browse/mkdir", response_model=None)
async def mkdir_in_workspace(body: MkdirRequest) -> JSONResponse:
    """Create a directory inside the workspace."""
    ws = _resolve_workspace(body.workspace)

    raw = body.path
    if not os.path.isabs(raw):
        raw = os.path.join(ws, raw)
    target = _validate_target(raw, ws, allow_sensitive=True)

    if os.path.exists(target):
        raise validation_error("Path already exists")

    dir_name = os.path.basename(target)
    _validate_name(dir_name)

    os.makedirs(target, exist_ok=False)
    return success_response(data={"path": target, "name": dir_name})


@router.post("/browse/rename", response_model=None)
async def rename_in_workspace(body: RenameRequest) -> JSONResponse:
    """Rename a file or directory inside the workspace."""
    ws = _resolve_workspace(body.workspace)

    raw = body.path
    if not os.path.isabs(raw):
        raw = os.path.join(ws, raw)
    source = _validate_target(raw, ws)

    if not os.path.exists(source):
        raise validation_error("Source does not exist")

    basename = os.path.basename(os.path.normpath(source))
    if basename in _PROTECTED_NAMES:
        raise validation_error(f"Cannot rename protected item: {basename}")

    _validate_name(body.new_name)

    parent = os.path.dirname(source)
    dest = os.path.join(parent, body.new_name)
    dest_resolved = _validate_target(dest, ws, allow_sensitive=True)

    if os.path.exists(dest_resolved):
        raise validation_error(f"A file or directory named '{body.new_name}' already exists")

    os.rename(source, dest_resolved)
    return success_response(
        data={
            "old_name": basename,
            "new_name": body.new_name,
            "path": dest_resolved,
        }
    )


@router.post("/browse/move", response_model=None)
async def move_in_workspace(body: MoveRequest) -> JSONResponse:
    """Move a file or directory to another directory inside the workspace."""
    ws = _resolve_workspace(body.workspace)

    src_raw = body.source
    if not os.path.isabs(src_raw):
        src_raw = os.path.join(ws, src_raw)
    source = _validate_target(src_raw, ws)

    if not os.path.exists(source):
        raise validation_error("Source does not exist")

    tgt_raw = body.target_dir
    if not os.path.isabs(tgt_raw):
        tgt_raw = os.path.join(ws, tgt_raw)
    target_dir = _validate_target(tgt_raw, ws, allow_sensitive=True)

    if not os.path.isdir(target_dir):
        raise validation_error("Target directory does not exist")

    basename = os.path.basename(os.path.normpath(source))
    dest = os.path.join(target_dir, basename)
    dest_resolved = _validate_target(dest, ws, allow_sensitive=True)

    if os.path.exists(dest_resolved):
        raise validation_error(f"'{basename}' already exists in target directory")

    shutil.move(source, dest_resolved)
    return success_response(
        data={
            "name": basename,
            "old_path": source,
            "new_path": dest_resolved,
        }
    )


@router.delete("/browse/delete", response_model=None)
async def delete_in_workspace(
    workspace: str = Query(..., description="Workspace root path"),
    path: str = Query(..., description="File or directory to delete"),
) -> JSONResponse:
    """Delete a file or directory from the workspace.

    Protected items (.git, workspace root) cannot be deleted.  Directories
    with more than 500 entries are rejected as a safety measure.
    """
    ws = _resolve_workspace(workspace)

    raw = path
    if not os.path.isabs(raw):
        raw = os.path.join(ws, raw)
    target = _validate_target(raw, ws)

    if not os.path.exists(target):
        raise validation_error("Path does not exist")

    target_real = os.path.realpath(target)
    ws_real = os.path.realpath(ws)
    if target_real == ws_real:
        raise validation_error("Cannot delete workspace root")

    basename = os.path.basename(os.path.normpath(target))
    if basename in _PROTECTED_NAMES:
        raise validation_error(f"Cannot delete protected item: {basename}")

    is_dir = os.path.isdir(target)
    if is_dir:
        entry_count = _count_entries(target)
        if entry_count > _MAX_DELETE_ENTRIES:
            raise validation_error(
                f"Directory contains {entry_count}+ entries (limit {_MAX_DELETE_ENTRIES}). "
                f"Use the agent to delete large directories."
            )
        shutil.rmtree(target)
    else:
        os.remove(target)

    return success_response(
        data={
            "deleted": basename,
            "type": "directory" if is_dir else "file",
        }
    )


@router.put("/browse/content", response_model=None)
async def save_workspace_file(body: SaveContentRequest) -> JSONResponse:
    """Save text content to a workspace file (online editor).

    Creates the file if it does not exist.  Only text content within the
    size limit is accepted.
    """
    if len(body.content.encode("utf-8")) > _MAX_CONTENT_SAVE_SIZE:
        raise validation_error(f"Content exceeds {_MAX_CONTENT_SAVE_SIZE // (1024 * 1024)}MB limit")

    ws = _resolve_workspace(body.workspace)

    raw = body.path
    if not os.path.isabs(raw):
        raw = os.path.join(ws, raw)
    target = _validate_target(raw, ws)

    if os.path.isdir(target):
        raise validation_error("Cannot write content to a directory")

    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        raise validation_error("Parent directory does not exist")

    with open(target, "w", encoding="utf-8") as f:
        f.write(body.content)

    size = os.path.getsize(target)
    return success_response(
        data={
            "path": target,
            "name": os.path.basename(target),
            "size": size,
        }
    )
