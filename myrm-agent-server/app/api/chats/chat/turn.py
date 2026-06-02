from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


class RegenerateRequest(BaseModel):
    instruction: str | None = None


class SwitchSiblingRequest(BaseModel):
    sibling_group_id: str
    target_message_id: str


@router.post("/{chat_id}/retry", response_model=StandardSuccessResponse)
async def retry_last_turn(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete the last assistant turn so the original query can be re-sent.

    Returns the original user query and the number of deleted messages.
    Idempotent: safe to call multiple times.
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        result = await ChatService.retry_last_turn(chat_id)
        return success_response(
            data={
                "success": result.success,
                "query": result.query,
                "deleted_count": result.deleted_count,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Retry last turn", exception=e) from e


@router.post("/{chat_id}/regenerate", response_model=StandardSuccessResponse)
async def regenerate_last_turn(
    chat_id: str,
    body: RegenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Mark the last assistant turn as inactive sibling and return query for re-generation.

    Unlike retry (which deletes), this preserves old responses for sibling navigation.
    Optional instruction field allows users to provide guidance (e.g. "be more concise").
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

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

        ok = await ChatService.switch_sibling(body.sibling_group_id, body.target_message_id)
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


@router.post("/{chat_id}/undo", response_model=StandardSuccessResponse)
async def undo_last_turn(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete the entire last turn (user message + assistant responses).

    Idempotent: safe to call on an empty chat.
    """
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        result = await ChatService.undo_last_turn(chat_id)
        return success_response(
            data={
                "success": result.success,
                "deleted_count": result.deleted_count,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Undo last turn", exception=e) from e

