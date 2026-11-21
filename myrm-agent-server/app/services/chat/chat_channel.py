"""Channel chat resolution mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- database.dto::ChatDTO (POS: 数据传输对象)

[OUTPUT]
- _ChatChannelMixin: 按渠道会话键查找、并发安全地创建渠道聊天

[POS]
渠道（IM / bot）聊天的解析层：一个渠道会话键对应一个聊天；命中且无需改绑只读不写，创建与改绑起手取写锁并在锁内回读，同键的并发创建者收敛到同一个聊天。
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.database.dto import ChatDTO
from app.database.repositories.channel_key_match import channel_key_extends
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase


def _needs_rebind(chat: ChatDTO, agent_id: str | None) -> bool:
    """Whether ``chat`` is bound to another agent than the one the caller resolved (no agent leaves the binding as is)."""
    return bool(agent_id) and chat.agent_id != agent_id


class _ChatChannelMixin(_ChatServiceBase):
    """Channel chat lookup and creation."""

    @staticmethod
    async def get_channel_chat_by_key(session_key: str) -> ChatDTO | None:
        """Resolve the channel chat stored under ``session_key``."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_channel_chat_by_key(session_key)

    @staticmethod
    async def get_newest_channel_chat_under(base_key: str) -> ChatDTO | None:
        """Return the most recently active Chat whose key is ``base_key`` or extends it.

        ``channel_session_key`` appends the reset epoch and the bound agent, so the key a caller
        can build is not always the one stored. An extension continues after a ``:`` segment
        boundary, so ``…:peer-a`` never matches ``…:peer-ab`` (see ``channel_key_extends``).
        """
        from sqlalchemy import select

        from app.database.models import Chat

        async with UnitOfWork() as uow:
            assert uow.session is not None
            result = await uow.session.execute(
                select(Chat.channel_session_key).where(channel_key_extends(base_key)).order_by(Chat.updated_at.desc()).limit(1)
            )
            row = result.first()
            if row is None:
                return None
            return await _ChatServiceBase._cr(uow).get_channel_chat_by_key(str(row[0]))

    @staticmethod
    async def get_or_create_channel_chat(
        session_key: str,
        source: str,
        *,
        agent_id: str | None = None,
    ) -> ChatDTO:
        """Return the chat stored under ``session_key``; create it, or rebind it to ``agent_id``, when needed.

        A chat that exists and needs no rebind comes back from a plain read, which no writer can hold back. Creating or
        rebinding reads and then writes, and nothing retries it (the message that triggered the lookup is answered with
        an error and dropped), so that unit takes the write lock first and reads again under it: a writer committing
        between the read and the write would abort the write with ``database is locked``, and of two creators of one key
        the second finds the chat the first created. The caller must not hold a write transaction of its own, which this
        unit would then wait for.
        """
        async with UnitOfWork() as uow:
            existing = await _ChatServiceBase._cr(uow).get_channel_chat_by_key(session_key)
        if existing and not _needs_rebind(existing, agent_id):
            return existing

        async with UnitOfWork(write=True) as uow:
            chats = _ChatServiceBase._cr(uow)
            chat = await chats.get_channel_chat_by_key(session_key)
            if chat is None:
                now = datetime.utcnow()
                chat = ChatDTO(
                    id=str(uuid4()),
                    agent_id=agent_id,
                    source=source,
                    channel_session_key=session_key,
                    created_at=now,
                    updated_at=now,
                )
                await chats.add_chat(chat)
            elif _needs_rebind(chat, agent_id):
                await chats.update_chat_fields(chat.id, {"agent_id": agent_id})
                chat = chat.model_copy(update={"agent_id": agent_id})
            return chat
