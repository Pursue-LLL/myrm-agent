"""Chat session loop HTTP routes.

[INPUT]
- app.services.loop.session_loop_manager::SessionLoopManager (POS: loop lifecycle manager)

[OUTPUT]
- router:
  - POST /{chat_id}/loop/start
  - POST /{chat_id}/loop/stop
  - GET /{chat_id}/loop/status

[POS]
HTTP boundary for session-scoped loop scheduling.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.loop import SessionLoopManager

router = APIRouter()


class StartLoopBody(BaseModel):
    command: str = Field(..., description="Full /loop command string or task prompt")

    class Config:
        populate_by_name = True


class StopLoopBody(BaseModel):
    reason: str = Field("user_stopped", description="Optional stop reason")

    class Config:
        populate_by_name = True


@router.post("/{chat_id}/loop/start", response_model=StandardSuccessResponse)
async def start_session_loop(
    chat_id: str,
    body: StartLoopBody,
) -> JSONResponse:
    """Start or update an active loop for the given chat session."""
    manager = SessionLoopManager.get_instance()
    result = await manager.start_loop(chat_id, body.command)
    if not result.success:
        raise validation_error(result.error or "Failed to start loop")

    return success_response(
        data=result.status.to_dict() if result.status else {},
    )


@router.post("/{chat_id}/loop/stop", response_model=StandardSuccessResponse)
async def stop_session_loop(
    chat_id: str,
    body: StopLoopBody | None = None,
) -> JSONResponse:
    """Stop active loop for the given chat session."""
    manager = SessionLoopManager.get_instance()
    stopped = await manager.stop_loop(chat_id)
    if not stopped:
        # Check if already stopped or never existed
        status = await manager.get_status(chat_id)
        if status is None:
            raise not_found_error("No active loop found for this session")

    status = await manager.get_status(chat_id)
    return success_response(
        data=status.to_dict() if status else {},
    )


@router.get("/{chat_id}/loop/status", response_model=StandardSuccessResponse)
async def get_session_loop_status(
    chat_id: str,
) -> JSONResponse:
    """Retrieve current loop status for the given chat session."""
    manager = SessionLoopManager.get_instance()
    status = await manager.get_status(chat_id)
    if status is None:
        return success_response(
            data={"is_active": False, "status": "none"},
        )

    return success_response(
        data=status.to_dict(),
    )
