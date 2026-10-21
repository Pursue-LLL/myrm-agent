from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    UpdateSummaryRequest,
)
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


class CompactRequest(BaseModel):
    focus_topic: str = Field(default="", max_length=200)


@router.post("/{chat_id}/compact", response_model=StandardSuccessResponse)
async def compact_chat(
    chat_id: str,
    body: CompactRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Compact chat context by generating a persistent summary.

    Original messages are preserved — the summary is used by the Agent
    layer to reduce token cost on subsequent interactions.
    """
    from app.services.chat.compact_service import compact_chat as do_compact

    focus_topic = body.focus_topic.strip() if body and body.focus_topic else ""

    try:
        result = await do_compact(db, chat_id, focus_topic=focus_topic)
        return success_response(
            data={
                "compacted": result.compacted,
                "original_tokens": result.original_tokens,
                "summary_tokens": result.summary_tokens,
                "tokens_saved": result.tokens_saved,
                "message_count": result.message_count,
                "backup_path": result.backup_path,
                "reason": result.reason,
                "focus_topic": focus_topic,
            }
        )
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Compact chat context", exception=e) from e


@router.put("/{chat_id}/compaction/summary", response_model=StandardSuccessResponse)
async def update_compaction_summary(
    chat_id: str,
    body: UpdateSummaryRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Update compaction summary for a chat session (admin override API)."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        await ChatService.update_compaction_summary(chat_id, body.summary)
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update compaction summary", exception=e) from e


@router.get("/{chat_id}/archive", response_model=StandardSuccessResponse)
async def get_chat_archive(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Retrieve archived messages from compacted history (read-only, does not affect prefix cache)."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        from app.services.chat.compact_service import get_archived_messages

        messages = await get_archived_messages(chat_id)
        return success_response(data={"messages": messages})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get chat archive", exception=e) from e


class PinFilesRequest(BaseModel):
    files: list[str] = Field(default_factory=list)


class PinFileRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=1024)


class ContextBranchRequest(BaseModel):
    snapshot_path: str = Field(min_length=1, max_length=2048)
    label: str = Field(default="", max_length=120)


@router.get("/{chat_id}/context/pins", response_model=StandardSuccessResponse)
async def get_context_pins(chat_id: str) -> JSONResponse:
    from myrm_agent_harness.runtime.context.session.session_context_pins import (
        read_pinned_files,
    )

    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")
    return success_response(data={"files": read_pinned_files(chat_id)})


@router.put("/{chat_id}/context/pins", response_model=StandardSuccessResponse)
async def set_context_pins(chat_id: str, body: PinFilesRequest) -> JSONResponse:
    from myrm_agent_harness.runtime.context.session.session_context_pins import (
        write_pinned_files,
    )

    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")
    record = write_pinned_files(chat_id, body.files)
    return success_response(data={"files": list(record.files), "updated_at": record.updated_at})


@router.post("/{chat_id}/context/pins", response_model=StandardSuccessResponse)
async def add_context_pin(chat_id: str, body: PinFileRequest) -> JSONResponse:
    from myrm_agent_harness.runtime.context.session.session_context_pins import (
        add_pinned_file,
    )

    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")
    record = add_pinned_file(chat_id, body.file_path)
    return success_response(data={"files": list(record.files), "updated_at": record.updated_at})


@router.get("/{chat_id}/context/branches", response_model=StandardSuccessResponse)
async def list_context_branches(chat_id: str) -> JSONResponse:
    from myrm_agent_harness.runtime.context.context_branches import list_context_branches as list_branches

    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")
    branches = [
        {
            "branch_id": item.branch_id,
            "label": item.label,
            "snapshot_path": item.snapshot_path,
            "created_at": item.created_at,
        }
        for item in list_branches(chat_id)
    ]
    return success_response(data={"branches": branches})


@router.post("/{chat_id}/context/branches", response_model=StandardSuccessResponse)
async def create_context_branch(chat_id: str, body: ContextBranchRequest) -> JSONResponse:
    from myrm_agent_harness.runtime.context.context_branches import append_context_branch

    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")
    record = append_context_branch(
        chat_id,
        snapshot_path=body.snapshot_path,
        label=body.label,
    )
    return success_response(
        data={
            "branch_id": record.branch_id,
            "label": record.label,
            "snapshot_path": record.snapshot_path,
            "created_at": record.created_at,
        }
    )


class BranchForkRequest(BaseModel):
    new_title: str = Field(default="", max_length=255)


@router.post("/{chat_id}/context/branches/{branch_id}/fork", response_model=StandardSuccessResponse)
async def fork_context_branch(
    chat_id: str,
    branch_id: str,
    body: BranchForkRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Fork a new chat from a snapshot bookmark (pre-compaction conversation restore)."""
    from app.services.chat.context_branch_fork import ContextBranchForkService

    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")

    new_title = body.new_title.strip() if body and body.new_title else None
    result = await ContextBranchForkService.fork_from_branch(
        db,
        chat_id,
        branch_id,
        new_title=new_title,
    )
    if not result.success or result.new_chat_id is None:
        raise validation_error(result.error or "Failed to fork from snapshot bookmark")

    return success_response(
        data={
            "new_chat_id": result.new_chat_id,
            "parent_chat_id": result.parent_chat_id,
            "branch_id": result.branch_id,
            "message_count": result.message_count,
        }
    )
