"""[INPUT]
- .common (POS: shared router, models and helpers)

[OUTPUT]
- browse_content

[POS]
Workspace browse API: file content preview/download.
"""

from __future__ import annotations

import mimetypes
import os

from fastapi import Query
from fastapi.responses import FileResponse, Response

from app.core.utils.errors import validation_error

from .common import (
    _MAX_CONTENT_SIZE,
    _content_disposition,
    _is_text_file,
    _is_within_boundary,
    router,
)


@router.get("/browse/content", response_model=None)
async def browse_content(
    path: str = Query(
        ...,
        description="Absolute file path, or path relative to the resolved workspace when using chat_id/workspace",
    ),
    workspace: str | None = Query(None, description="Workspace root boundary (omit when chat_id is provided)"),
    chat_id: str | None = Query(
        None,
        description="Chat id — resolves workspace root via Chat metadata (JIT sandbox bind when unset)",
    ),
    download: bool = Query(False, description="True to trigger download instead of inline preview"),
) -> Response:
    """Read file content for preview or download.

    Text files are returned inline with a 1MB truncation guard. Binary
    files (images/PDF/audio/video/office docs) are streamed in full via
    ``FileResponse`` — no size limit, with HTTP Range support so rich
    media previews and seeking work for large files.

    Either ``workspace`` or ``chat_id`` must be provided so the server can
    establish the allowed root (matches Active Files previews when the
    UI has not yet synced ``workspace_dir`` into client state).
    """
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path, is_sensitive_file

    from app.services.chat.chat_service import ChatService

    workspace_resolved: str | None = None
    if workspace and workspace.strip():
        workspace_resolved = os.path.realpath(os.path.expanduser(workspace.strip()))
    elif chat_id and chat_id.strip():
        from app.services.chat.effective_workspace import resolve_effective_chat_workspace

        meta = await ChatService.get_chat_metadata(chat_id.strip())
        if meta is None:
            raise validation_error("Unknown chat_id")
        ws = await resolve_effective_chat_workspace(
            meta,
            jit_fallback=True,
            persist_jit=False,
        )
        if not ws:
            raise validation_error("Could not resolve workspace for chat")
        workspace_resolved = os.path.realpath(os.path.expanduser(ws.strip()))
    else:
        raise validation_error("Either workspace or chat_id is required")

    raw_path = os.path.expanduser(path)
    if os.path.isabs(raw_path):
        resolved = os.path.realpath(raw_path)
    else:
        resolved = os.path.realpath(os.path.join(workspace_resolved, raw_path))

    if is_dangerous_path(resolved):
        raise validation_error(f"Access denied: {path}")

    if not _is_within_boundary(resolved, workspace_resolved):
        raise validation_error("File is outside workspace boundary")

    if is_sensitive_file(resolved):
        raise validation_error("Access denied: sensitive file")

    if not os.path.isfile(resolved):
        raise validation_error(f"Not a file: {path}")

    file_size = os.path.getsize(resolved)

    filename = os.path.basename(resolved)
    content_type, _ = mimetypes.guess_type(filename)
    is_text = _is_text_file(filename)
    if content_type is None:
        content_type = "text/plain" if is_text else "application/octet-stream"

    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": _content_disposition(disposition, filename),
    }

    # Binary files are streamed in full (no truncation) so rich media
    # previews — images, PDFs, audio/video, office docs — render correctly.
    # FileResponse handles HTTP Range requests, enabling seeking for media.
    if not is_text:
        return FileResponse(
            resolved,
            media_type=content_type,
            headers=headers,
        )

    is_truncated = file_size > _MAX_CONTENT_SIZE

    try:
        with open(resolved, "rb") as f:
            if is_truncated:
                content = f.read(_MAX_CONTENT_SIZE)
            else:
                content = f.read()
    except PermissionError:
        raise validation_error(f"Permission denied: {path}") from None
    except OSError as e:
        raise validation_error(f"Cannot read file: {e}") from e

    headers["Content-Length"] = str(len(content))
    if is_truncated:
        headers["X-Content-Truncated"] = "true"

    return Response(
        content=content,
        media_type=content_type,
        headers=headers,
    )
