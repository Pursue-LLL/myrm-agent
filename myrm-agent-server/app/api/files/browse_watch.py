"""Workspace file watch registration API.

[INPUT]
- app.services.workspace.file_watch_service::get_workspace_file_watch_service
- app.core.utils.errors::validation_error
- app.core.utils.response_utils::success_response

[OUTPUT]
- POST /browse/watch — Register refcounted workspace directory watch
- DELETE /browse/watch — Release workspace directory watch

[POS]
HTTP layer for P1 workspace vault change notifications. Pairs with
useWorkspaceFiles SSE auto-refresh on the Web/SaaS file browser.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response
from app.services.workspace.file_watch_service import (
    get_workspace_file_watch_service,
    resolve_watchable_workspace_path,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class WorkspaceWatchRequest(BaseModel):
    workspace: str = Field(..., min_length=1, description="Absolute workspace root to watch")


@router.post("/browse/watch", response_model=None)
async def register_workspace_watch(body: WorkspaceWatchRequest) -> JSONResponse:
    """Start (or increment refcount for) a recursive watch on a workspace directory."""
    try:
        resolved = resolve_watchable_workspace_path(body.workspace)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc

    try:
        await get_workspace_file_watch_service().acquire(resolved)
    except RuntimeError as exc:
        raise validation_error(str(exc)) from exc

    return success_response(data={"workspace": resolved})


@router.delete("/browse/watch", response_model=None)
async def unregister_workspace_watch(
    workspace: str = Query(..., description="Workspace root previously registered for watch"),
) -> JSONResponse:
    """Release a workspace directory watch registration."""
    try:
        resolved = resolve_watchable_workspace_path(workspace)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc

    await get_workspace_file_watch_service().release(resolved)
    return success_response(data={"workspace": resolved})
