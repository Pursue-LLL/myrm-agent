"""Chat turn HTTP routes: regenerate, sibling switching and edit-resend truncation.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: chat business facade)
- app.services.chat.session_continuity_service::CheckpointClearError (POS: checkpoint-clear failure after a history mutation)
- app.services.risk.refusal::reject_if_risky (POS: refuses a regeneration guidance a risk rule holds)

[OUTPUT]
- router: POST /{chat_id}/regenerate, POST /{chat_id}/switch-sibling, GET /{chat_id}/siblings/{sibling_group_id},
  POST /{chat_id}/truncate-after

[POS]
Turn-level mutation endpoints of the chat API. Going back to an earlier message is `rewind.py`; IM retry and undo
call the service layer directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.session_continuity_service import CheckpointClearError
from app.services.risk.refusal import reject_if_risky

router = APIRouter()


class RegenerateRequest(BaseModel):
    instruction: str | None = None


class TruncateAfterRequest(BaseModel):
    message_id: str


class SwitchSiblingRequest(BaseModel):
    sibling_group_id: str
    target_message_id: str


@router.post("/{chat_id}/regenerate", response_model=StandardSuccessResponse)
async def regenerate_last_turn(
    chat_id: str,
    body: RegenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Mark the last assistant turn as inactive sibling and return query for re-generation.

    Unlike retry (which deletes), this preserves old responses for sibling navigation.
    Optional instruction field allows users to provide guidance (e.g. "be more concise"); a guidance a risk rule
    holds is refused before the last turn is touched.
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        await reject_if_risky(body.instruction if body else None, session_id=chat_id)

        result = await ChatService.regenerate_last_turn(chat_id)
        if not result.success:
            raise not_found_error("User message")

        return success_response(
            data={
                "success": True,
                "query": result.query,
                "sibling_group_id": result.sibling_group_id,
                "instruction": body.instruction if body else None,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Regenerate last turn", exception=e) from e


@router.post("/{chat_id}/switch-sibling", response_model=StandardSuccessResponse)
async def switch_sibling(
    chat_id: str,
    body: SwitchSiblingRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Switch the active sibling within a sibling group."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        ok = await ChatService.switch_sibling(chat_id, body.sibling_group_id, body.target_message_id)
        if not ok:
            raise not_found_error("Sibling message")

        return success_response(data={"success": True})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Switch sibling", exception=e) from e


@router.get("/{chat_id}/siblings/{sibling_group_id}", response_model=StandardSuccessResponse)
async def get_siblings(
    chat_id: str,
    sibling_group_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get all siblings in a group with their active status."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        siblings = await ChatService.get_sibling_info(sibling_group_id)
        return success_response(data={"siblings": siblings})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get siblings", exception=e) from e


@router.post("/{chat_id}/truncate-after", response_model=StandardSuccessResponse)
async def truncate_after_message(
    chat_id: str,
    body: TruncateAfterRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete the specified message and all messages after it.

    Used by edit-resend to keep backend state consistent with the
    frontend before the user re-sends a modified message.
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        result = await ChatService.truncate_after_message(chat_id, body.message_id)
        return success_response(
            data={
                "success": result.success,
                "deleted_count": result.deleted_count,
            }
        )
    except HTTPException:
        raise
    except CheckpointClearError as exc:
        raise internal_error(operation="Truncate after message", exception=exc) from exc
    except Exception as e:
        raise internal_error(operation="Truncate after message", exception=e) from e
