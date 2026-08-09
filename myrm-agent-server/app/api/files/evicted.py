"""Evicted output file reader API.

Securely serves full outputs evicted (saved to disk) during tool execution
when they exceeded the delivery threshold. Provides line-range reading and
graceful expiration handling.

[INPUT]
- myrm_agent_harness.agent.context_management.infra.evicted_reader (POS: paginated evicted file I/O)
- myrm_agent_harness.agent.context_management.infra.evicted_content::normalize_delivery_chat_id (POS: UECD delivery SSOT)
- myrm_agent_harness.api.hooks::EVICTED_BASENAME_PATTERN (POS: spill filename validation)

[OUTPUT]
- GET /evicted: paginated line-range read (default limit 500)

[POS]
Evicted tool output reader endpoint. Allows GUI users to view full tool outputs
that were offloaded to disk during agent execution.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.context_management.infra.evicted_content import (
    normalize_delivery_chat_id,
)
from myrm_agent_harness.agent.context_management.infra.evicted_reader import (
    read_evicted_line_range,
)
from myrm_agent_harness.api.hooks import EVICTED_BASENAME_PATTERN

from app.config.deploy_mode import is_local_mode

logger = logging.getLogger(__name__)

router = APIRouter()

_FILENAME_PATTERN = EVICTED_BASENAME_PATTERN
_DEFAULT_PAGE_LIMIT = 500
_MAX_PAGE_LIMIT = 1000


async def _get_evicted_workspace_root(chat_id: str) -> str | None:
    """Resolve the workspace root that holds `.context/{chat_id}/evicted/`."""
    try:
        from app.services.chat.chat_service import ChatService
        from app.services.chat.effective_workspace import resolve_effective_chat_workspace

        chat = await ChatService.get_chat_by_id(chat_id)
        if chat is not None:
            resolved = await resolve_effective_chat_workspace(
                chat,
                jit_fallback=True,
                persist_jit=False,
            )
            if resolved and os.path.isdir(resolved):
                return resolved
    except Exception as exc:
        logger.warning(
            "Failed to resolve effective chat workspace for evicted read (chat_id=%s): %s",
            chat_id,
            exc,
        )

    try:
        from app.services.agent.params.workspace_resolve import (
            resolve_default_chat_workspace_dir,
        )

        resolved = await resolve_default_chat_workspace_dir(
            chat_id, persist_workspace=False
        )
        if resolved and os.path.isdir(resolved):
            return resolved
    except Exception as exc:
        logger.warning(
            "Failed to resolve default chat workspace for evicted read (chat_id=%s): %s",
            chat_id,
            exc,
        )

    env_root = os.environ.get("MYRM_WORKSPACE_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root

    return _get_workspace_root()


async def _resolve_evicted_path(chat_id: str, filename: str) -> str:
    """Resolve the absolute path to an evicted output file with security checks.

    The evicted outputs live in .context/{session_id}/evicted/ within the chat workspace.
    """
    if not _FILENAME_PATTERN.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if ".." in chat_id or "/" in chat_id or "\\" in chat_id:
        raise HTTPException(status_code=400, detail="Invalid chat_id")

    normalized_chat_id = normalize_delivery_chat_id(chat_id)

    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    workspace_root = await _get_evicted_workspace_root(chat_id)
    if not workspace_root:
        raise HTTPException(status_code=500, detail="Workspace root unavailable")

    evicted_dir = os.path.join(
        workspace_root, ".context", normalized_chat_id, "evicted"
    )
    resolved = os.path.realpath(os.path.join(evicted_dir, filename))

    if is_dangerous_path(resolved):
        raise HTTPException(status_code=403, detail="Access denied")

    expected_prefix = os.path.realpath(evicted_dir)
    if not resolved.startswith(expected_prefix + os.sep):
        raise HTTPException(
            status_code=403, detail="Access denied: path traversal detected"
        )

    return resolved


def _get_workspace_root() -> str | None:
    """Get the workspace root from harness runtime or environment."""
    workspace = os.environ.get("MYRM_WORKSPACE_ROOT")
    if workspace and os.path.isdir(workspace):
        return workspace

    try:
        from myrm_agent_harness.toolkits.code_execution.workspace.registry import (
            get_active_workspace_path,
        )

        return get_active_workspace_path()
    except Exception:
        pass

    if is_local_mode():
        home = os.path.expanduser("~")
        default_workspace = os.path.join(home, ".myrm", "workspace")
        if os.path.isdir(default_workspace):
            return default_workspace

    return None


@router.get("/evicted", response_model=None)
async def read_evicted_output(
    chat_id: str = Query(
        ..., description="Chat/session ID that produced the evicted output"
    ),
    filename: str = Query(
        ..., description="Evicted output filename (e.g. web_fetch_a3f5c8d1.md)"
    ),
    offset: int = Query(
        0, ge=0, description="Line offset to start reading from (0-based)"
    ),
    limit: int = Query(
        _DEFAULT_PAGE_LIMIT,
        ge=1,
        le=_MAX_PAGE_LIMIT,
        description="Number of lines to return",
    ),
) -> dict[str, object] | JSONResponse:
    """Read a paginated slice of an evicted tool output file.

    Returns JSON ``{"expired": true}`` with HTTP 404 when the file has been cleaned up.
    """
    resolved = await _resolve_evicted_path(chat_id, filename)

    if not os.path.isfile(resolved):
        return JSONResponse(status_code=404, content={"expired": True})

    try:
        page = read_evicted_line_range(
            resolved,
            offset=offset,
            limit=limit,
        )
        return {
            "content": page.content,
            "total_lines": page.total_lines,
            "stored_chars": page.stored_chars,
            "offset": page.offset,
            "limit": page.limit,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        logger.warning("Failed to read evicted file %s: %s", resolved, exc)
        raise HTTPException(status_code=500, detail="Failed to read file") from exc
