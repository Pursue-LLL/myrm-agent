import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from myrm_agent_harness.agent.streaming.broadcast.catchup import CatchupBriefExtractor
from sqlalchemy import select

from app.api.dependencies import get_deploy_identity
from app.core.utils.response_utils import success_response
from app.database.models.approval import ApprovalRecord as ApprovalRecord
from app.database.models.chat import Chat, Message, OfflineDurableTask
from app.platform_utils import get_session_factory

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/catchup")
async def get_catchup_briefs(user_id: str = Depends(get_deploy_identity)) -> Any:
    """Get catchup briefs for all chats with unread activity."""
    session_factory = get_session_factory()

    briefs: dict[str, dict[str, Any]] = {}

    async with session_factory() as db:
        # Find chats where updated_at > last_read_at (or last_read_at is None)
        # We only care about web source for now to avoid noise from background cron jobs
        stmt = (
            select(Chat)
            .where(Chat.source == "web", (Chat.last_read_at.is_(None)) | (Chat.updated_at > Chat.last_read_at))
            .order_by(Chat.updated_at.desc())
            .limit(20)
        )

        result = await db.execute(stmt)
        chats = result.scalars().all()

        if not chats:
            return success_response(data={"briefs": []})

        for chat in chats:
            # Determine status
            status = "completed"

            # Check if running offline
            task_stmt = select(OfflineDurableTask).where(OfflineDurableTask.chat_id == chat.id)
            task_result = await db.execute(task_stmt)
            if task_result.scalars().first():
                status = "running"

            # Check if waiting for approval
            approval_stmt = select(ApprovalRecord).where(ApprovalRecord.chat_id == chat.id, ApprovalRecord.status == "PENDING")
            approval_result = await db.execute(approval_stmt)
            if approval_result.scalars().first():
                status = "waiting_for_approval"

            # Fetch unread messages
            msg_stmt = select(Message).where(Message.chat_id == chat.id)
            if chat.last_read_at:
                msg_stmt = msg_stmt.where(Message.created_at > chat.last_read_at)

            msg_stmt = msg_stmt.order_by(Message.created_at.asc())
            msg_result = await db.execute(msg_stmt)
            messages = msg_result.scalars().all()

            if not messages and status != "running":
                continue

            # Prepare data for extractor
            msg_dicts = []
            progress_steps = []

            for msg in messages:
                msg_dicts.append({"role": msg.role, "content": msg.content})

                if msg.extra_data and isinstance(msg.extra_data, dict):
                    steps = msg.extra_data.get("progressSteps")
                    if isinstance(steps, list):
                        progress_steps.extend(steps)

            # Extract brief
            brief = CatchupBriefExtractor.extract(messages=msg_dicts, progress_steps=progress_steps, status=status)

            # Only include if there's actual activity or it's waiting
            if brief.activity_steps or brief.files_touched or status != "completed" or brief.latest_agent_response:
                brief_dict = brief.model_dump()
                brief_dict["chat_id"] = chat.id
                brief_dict["chat_title"] = chat.title or "Untitled Chat"
                brief_dict["updated_at"] = chat.updated_at.isoformat()
                briefs[chat.id] = brief_dict

    return success_response(data={"briefs": list(briefs.values())})


@router.post("/{chat_id}/read")
async def mark_chat_as_read(chat_id: str, user_id: str = Depends(get_deploy_identity)) -> Any:
    """Mark a chat as read, updating last_read_at to now."""
    session_factory = get_session_factory()

    async with session_factory() as db:
        stmt = select(Chat).where(Chat.id == chat_id)
        result = await db.execute(stmt)
        chat = result.scalars().first()

        if not chat:
            return success_response(message="Chat not found", code=404)

        chat.last_read_at = datetime.utcnow()
        await db.commit()

    return success_response(data={"success": True, "chat_id": chat_id})
