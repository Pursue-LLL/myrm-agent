"""Catchup inbox API: what happened in web chats while the user was away, and read marking.

[INPUT]
- app.api.dependencies::get_deploy_identity (POS: API 层统一依赖注入入口。所有 FastAPI 端点的依赖应从此模块导入)
- app.core.utils.response_utils::success_response (POS: 统一 API 响应格式工具。封装标准化的成功/列表/分页/错误响应构造)
- app.database.models.approval::ApprovalRecord (POS: 统一审批记录模型。存储所有被拦截的执行节点的挂起状态)
- app.database.models.chat::Chat, Message (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
- app.platform_utils::get_session_factory (POS: 平台适配层。按 DEPLOY_MODE 选择平台实现，提供数据库会话工厂)
- app.services.agent.gateway::get_agent_gateway (POS: Agent 执行网关。并发控制、内存压力熔断、优雅排空、超时保护和可观测性)
- app.services.chat.catchup_brief (POS: bounded per-chat summary projection behind the inbox)
- app.services.chat.chat_helpers::WAKEUP_MESSAGE_ID_PREFIX (POS: id prefix of system-injected wakeup rows)
- app.services.copilot.run_digest_store::RunDigestStore (POS: in-process run phases; the only record of a turn that failed before persisting a reply)

[OUTPUT]
- get_catchup_briefs: GET /catchup, one brief per web chat the user has not caught up with.
  Status priority: waiting_for_approval (a blocked turn is still in flight, so it must outrank running) > running (a turn is in flight) > error/stopped (last turn failed or was cancelled after the user left) > completed (agent replied after the user left).
- mark_chat_as_read: POST /{chat_id}/read, stamps the user's presence (last_read_at) and answers 404 for an unknown chat

[POS]
Catchup inbox endpoints. ``Chat.last_read_at`` is the user's last presence in a chat; an agent reply newer than it is unseen.
A chat with no recorded presence (NULL) counts as read until something happens that needs the user.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from pydantic import BaseModel
from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_deploy_identity
from app.core.utils.response_utils import success_response
from app.database.models.approval import ApprovalRecord
from app.database.models.chat import Chat, Message
from app.platform_utils import get_session_factory
from app.services.agent.gateway import get_agent_gateway
from app.services.chat.catchup_brief import CatchupBrief, CatchupStatus, extract_catchup_brief
from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX
from app.services.copilot.run_digest_store import RunDigestStore

logger = logging.getLogger(__name__)
router = APIRouter()

INBOX_LIMIT = 20
# Bounds the rows scanned for one brief when the user has been away through a very long autonomous run.
UNSEEN_MESSAGE_CAP = 400


class CatchupItem(CatchupBrief):
    chat_id: str
    chat_title: str
    updated_at: str


class CatchupInbox(BaseModel):
    briefs: list[CatchupItem]


def _naive_utc(moment: datetime) -> datetime:
    """Normalize to the naive-UTC convention that ``Message.created_at`` and ``last_read_at`` are stored in."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


async def _unseen_failures(db: AsyncSession) -> dict[str, CatchupStatus]:
    """Chats whose last turn failed or was cancelled after the user last saw them.

    A failed turn persists no assistant row, so the in-process run digest is the only record of it.
    A server restart forgets it; such a chat then ends on an unanswered user message.
    """
    digests = {digest.chat_id: digest for digest in RunDigestStore.terminal_failures()}
    if not digests:
        return {}
    rows = await db.execute(select(Chat.id, Chat.last_read_at).where(Chat.id.in_(list(digests))))
    failures: dict[str, CatchupStatus] = {}
    for chat_id, last_read_at in rows:
        digest = digests[chat_id]
        ended_at = _naive_utc(datetime.fromisoformat(digest.updated_at))
        if last_read_at is None or ended_at > _naive_utc(last_read_at):
            failures[chat_id] = "error" if digest.phase == RunDigestPhase.ERROR else "stopped"
    return failures


async def _candidate_chats(
    db: AsyncSession, running_ids: Collection[str], failed_ids: Collection[str]
) -> list[tuple[str, str | None, datetime, datetime | None]]:
    """Newest web chats that hold something unseen: a reply, a running turn, a pending approval or a failure."""
    unseen_reply = exists().where(
        Message.chat_id == Chat.id,
        Message.role == "assistant",
        Message.is_active.is_(True),
        Message.created_at > Chat.last_read_at,
    )
    pending_approval = exists().where(ApprovalRecord.chat_id == Chat.id, ApprovalRecord.status == "PENDING")
    stmt = (
        select(Chat.id, Chat.title, Chat.updated_at, Chat.last_read_at)
        .where(
            Chat.source == "web",
            Chat.deleted_at.is_(None),
            or_(unseen_reply, pending_approval, Chat.id.in_({*running_ids, *failed_ids})),
        )
        .order_by(Chat.updated_at.desc())
        .limit(INBOX_LIMIT)
    )
    return [(row[0], row[1], row[2], row[3]) for row in await db.execute(stmt)]


async def _chat_brief_inputs(
    db: AsyncSession, chat_id: str, last_read_at: datetime | None
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Messages the user has not seen, preceded by the person's latest prompt, plus their progress steps."""
    unseen_stmt = (
        select(Message.id, Message.role, Message.content, Message.extra_data)
        .where(Message.chat_id == chat_id, Message.is_active.is_(True))
        .order_by(Message.created_at.desc())
        .limit(UNSEEN_MESSAGE_CAP)
    )
    if last_read_at is not None:
        unseen_stmt = unseen_stmt.where(Message.created_at > last_read_at)
    unseen = list(reversed((await db.execute(unseen_stmt)).all()))

    # The prompt predates the user's last presence, so it is rarely among the unseen rows.
    prompt_stmt = (
        select(Message.id, Message.role, Message.content)
        .where(
            Message.chat_id == chat_id,
            Message.role == "user",
            Message.is_active.is_(True),
            ~Message.id.startswith(WAKEUP_MESSAGE_ID_PREFIX, autoescape=True),
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    prompt = (await db.execute(prompt_stmt)).first()

    messages: list[dict[str, object]] = []
    if prompt is not None:
        messages.append({"id": prompt.id, "role": prompt.role, "content": prompt.content})
    progress_steps: list[dict[str, object]] = []
    for row in unseen:
        messages.append({"id": row.id, "role": row.role, "content": row.content})
        steps = row.extra_data.get("progressSteps") if isinstance(row.extra_data, dict) else None
        if isinstance(steps, list):
            progress_steps.extend(step for step in steps if isinstance(step, dict))
    return messages, progress_steps


@router.get("/catchup")
async def get_catchup_briefs(user_id: Annotated[str, Depends(get_deploy_identity)]) -> JSONResponse:
    """Get a catchup brief for every web chat the user has not caught up with."""
    running_ids = get_agent_gateway().active_session_ids()
    briefs: list[CatchupItem] = []

    async with get_session_factory()() as db:
        failures = await _unseen_failures(db)
        chats = await _candidate_chats(db, running_ids, failures.keys())
        approval_rows = await db.execute(
            select(ApprovalRecord.chat_id).where(
                ApprovalRecord.chat_id.in_([chat[0] for chat in chats]), ApprovalRecord.status == "PENDING"
            )
        )
        approval_ids = set(approval_rows.scalars())

        for chat_id, title, updated_at, last_read_at in chats:
            status: CatchupStatus = "completed"
            if chat_id in approval_ids:
                status = "waiting_for_approval"
            elif chat_id in running_ids:
                status = "running"
            elif chat_id in failures:
                status = failures[chat_id]

            messages, progress_steps = await _chat_brief_inputs(db, chat_id, last_read_at)
            brief = extract_catchup_brief(messages, progress_steps, status)
            briefs.append(
                CatchupItem(
                    **brief.model_dump(),
                    chat_id=chat_id,
                    chat_title=title or "",
                    updated_at=updated_at.isoformat(),
                )
            )

    return success_response(data=CatchupInbox(briefs=briefs).model_dump())


@router.post("/{chat_id}/read")
async def mark_chat_as_read(chat_id: str, user_id: Annotated[str, Depends(get_deploy_identity)]) -> JSONResponse:
    """Record that the user is present in the chat now.

    ``updated_at`` is pinned so that reading never reorders the sidebar, which sorts by activity.
    """
    async with get_session_factory()() as db:
        result = await db.execute(
            update(Chat)
            .where(Chat.id == chat_id)
            .values(last_read_at=datetime.utcnow(), updated_at=Chat.updated_at)
            .returning(Chat.id)
        )
        if result.first() is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        await db.commit()

    return success_response(data={"success": True, "chat_id": chat_id})
