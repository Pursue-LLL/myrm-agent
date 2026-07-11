from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.chat.conversation_fork_manager import ConversationForkManager

router = APIRouter()


class ForkConversationBody(BaseModel):
    message_index: int = Field(..., alias="message_index", description="0-based index, or -1 for last message")
    new_title: str | None = Field(None, alias="new_title")

    class Config:
        populate_by_name = True


@router.post("/{chat_id}/fork", response_model=StandardSuccessResponse)
async def fork_conversation(
    chat_id: str,
    request: ForkConversationBody,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Fork conversation from specific message index.

    Creates a new conversation branch with complete checkpoint state
    at the fork point. Preserves messages + agent_state + tool outputs.

    Request Body:
        - message_index (int): Message index to fork from (0-based, or -1 for last)
        - new_title (str, optional): Custom title for forked conversation

    Returns:
        - new_chat_id (str): ID of newly created fork
        - parent_chat_id (str): Original conversation ID
        - fork_point (int): Message index where fork occurred

    """
    try:
        message_index = request.message_index
        new_title = request.new_title

        if message_index < -1:
            raise validation_error("message_index must be >= -1")

        if message_index == -1:
            message_index = await ConversationForkManager.get_last_message_index(db, chat_id)
            if message_index is None:
                raise validation_error("Chat has no messages to fork from")

        result = await ConversationForkManager.fork_conversation(
            db=db,
            parent_chat_id=chat_id,
            message_index=message_index,
            new_title=new_title,
        )

        if not result.success:
            error_msg = result.error or "Fork failed"
            if "not found" in error_msg:
                raise not_found_error("Parent conversation")
            if "Invalid message_index" in error_msg or "only support" in error_msg:
                raise validation_error(error_msg)
            if "Checkpointer not initialized" in error_msg or "No checkpoint found" in error_msg:
                raise validation_error(error_msg)
            raise internal_error(
                operation="Fork conversation",
                exception=RuntimeError(error_msg),
            )

        return success_response(
            data={
                "new_chat_id": result.new_chat_id,
                "parent_chat_id": result.parent_chat_id,
                "fork_point": result.fork_point,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Fork conversation", exception=e) from e


@router.get("/{chat_id}/fork-info", response_model=StandardSuccessResponse)
async def get_fork_info(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get fork relationship information for a conversation.

    Returns:
        - parent_chat_id (str | null): Parent conversation ID (if forked)
        - fork_point (int | null): Message index where fork occurred
        - children (list): List of child forks with {chat_id, title, created_at}

    """
    try:
        # Verify user has access to this chat
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        fork_info = await ConversationForkManager.get_fork_info(db, chat_id)

        return success_response(
            data={
                "parent_chat_id": fork_info.parent_chat_id,
                "fork_point": fork_info.fork_point,
                "children": [
                    {
                        "chat_id": child.chat_id,
                        "title": child.title,
                        "created_at": child.created_at,
                    }
                    for child in fork_info.children
                ],
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get fork info", exception=e) from e
