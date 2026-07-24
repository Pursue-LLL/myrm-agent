"""Evicted output file reader API.

Securely serves full outputs evicted (saved to disk) during tool execution
when they exceeded the delivery threshold. Provides line-range reading and
graceful expiration handling.

[POS]
Evicted tool output reader endpoint. Allows GUI users to view full tool outputs
that were offloaded to disk during agent execution.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from myrm_agent_harness.api.hooks import EVICTED_BASENAME_PATTERN

from app.config.deploy_mode import is_local_mode

logger = logging.getLogger(__name__)

router = APIRouter()

_FILENAME_PATTERN = EVICTED_BASENAME_PATTERN


def _resolve_evicted_path(chat_id: str, filename: str) -> str:
    """Resolve the absolute path to an evicted output file with security checks.

    The evicted outputs live in .context/{session_id}/evicted/ within the workspace.
    For local mode, the workspace is discovered from the harness runtime.
    """
    if not _FILENAME_PATTERN.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if ".." in chat_id or "/" in chat_id or "\\" in chat_id:
        raise HTTPException(status_code=400, detail="Invalid chat_id")

    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    workspace_root = _get_workspace_root()
    if not workspace_root:
        raise HTTPException(status_code=500, detail="Workspace root unavailable")

    evicted_dir = os.path.join(workspace_root, ".context", chat_id, "evicted")
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


@router.get("/evicted")
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
    limit: int = Query(0, ge=0, description="Number of lines to return (0 = all)"),
) -> dict:
    """Read an evicted tool output file.

    Returns the full or partial content of a file that was saved during
    output eviction. Supports line-range pagination via offset/limit.

    Returns JSON ``{"expired": true}`` with HTTP 404 when the file has been cleaned up.
    """
    resolved = _resolve_evicted_path(chat_id, filename)

    if not os.path.isfile(resolved):
        return JSONResponse(status_code=404, content={"expired": True})

    try:
        with open(resolved, encoding="utf-8", errors="replace") as f:
            if limit > 0:
                lines = f.readlines()
                total_lines = len(lines)
                sliced = lines[offset : offset + limit]
                content = "".join(sliced)
                return {
                    "content": content,
                    "total_lines": total_lines,
                    "offset": offset,
                    "limit": limit,
                }
            else:
                content = f.read()
                total_lines = content.count("\n") + (
                    1 if content and not content.endswith("\n") else 0
                )
                return {
                    "content": content,
                    "total_lines": total_lines,
                }
    except OSError as e:
        logger.warning("Failed to read evicted file %s: %s", resolved, e)
        raise HTTPException(status_code=500, detail="Failed to read file") from e
