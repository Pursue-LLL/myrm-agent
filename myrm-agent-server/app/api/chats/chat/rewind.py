"""Chat rewind HTTP routes.

[INPUT]
- app.services.chat.session_continuity_service (POS: rewind execution)

[OUTPUT]
- router: POST /chats/{chat_id}/rewind endpoint

[POS]
HTTP boundary for checkpoint rewind actions in the chat API.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.session_continuity_service import ContinuitySyncError, SessionBusyError

router = APIRouter()


class RewindMessageBody(BaseModel):
    message_id: str = Field(..., alias="message_id")
    scope: Literal["conversation", "both"] = "conversation"

    class Config:
        populate_by_name = True


@router.post("/{chat_id}/rewind", response_model=StandardSuccessResponse)
async def rewind_to_message(
    chat_id: str,
    body: RewindMessageBody,
) -> JSONResponse:
    """Rewind conversation to before a user message and return composer seed text.

    ``scope`` selects what to roll back:
    - ``conversation`` (default): delete messages only, files untouched.
    - ``both``: also revert file changes made by the deleted messages so the
      workspace matches the state before the target message.
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        result = await ChatService.rewind_to_message(chat_id, body.message_id, revert_files=body.scope == "both")
        if result.error == "SESSION_BUSY":
            raise HTTPException(
                status_code=409,
                detail="Rewind is unavailable while the agent is working",
            )
        if result.error == "REWIND_USER_ONLY":
            raise validation_error("Rewind is only supported for user messages")
        if result.error in {"MESSAGE_NOT_FOUND", "NOTHING_TO_REWIND"}:
            raise validation_error(result.error or "Rewind failed")
        if not result.success:
            raise internal_error(
                operation="Rewind conversation",
                exception=RuntimeError(result.error or "Rewind failed"),
            )

        return success_response(
            data={
                "success": result.success,
                "deleted_count": result.deleted_count,
                "composer_text": result.composer_text,
                "message_index": result.message_index,
                "goal_paused": result.goal_paused,
                "reverted_files": result.reverted_files or [],
                "file_warnings": result.file_warnings or [],
                "skipped_files": result.skipped_files or [],
            }
        )
    except HTTPException:
        raise
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContinuitySyncError as exc:
        raise internal_error(operation="Rewind conversation", exception=exc) from exc
    except Exception as exc:
        raise internal_error(operation="Rewind conversation", exception=exc) from exc
