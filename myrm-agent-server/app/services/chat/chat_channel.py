"""Channel chat resolution mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- database.dto::ChatDTO (POS: 数据传输对象)

[OUTPUT]
- _ChatChannelMixin: 按渠道会话键查找、并发安全地创建渠道聊天

[POS]
渠道（IM / bot）聊天的解析层：一个渠道会话键对应一个聊天，并发首次创建时以唯一约束兜底并回读胜出者。
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.database.dto import ChatDTO
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase


class _ChatChannelMixin(_ChatServiceBase):
    """Channel chat lookup and creation."""

    @staticmethod
    async def get_channel_chat_by_key(user_id_or_session_key: str, session_key: str | None = None) -> ChatDTO | None:
        """Resolve channel chat; supports ``get_channel_chat_by_key(session_key)`` or
        ``get_channel_chat_by_key(user_id, session_key)`` (user_id is ignored for lookup).
        """
        key = session_key if session_key is not None else user_id_or_session_key
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_channel_chat_by_key(key)

    @staticmethod
    async def get_newest_channel_chat_under(base_key: str) -> ChatDTO | None:
        """Return the most recently active Chat whose key is ``base_key`` or extends it.

        ``channel_session_key`` appends the reset epoch and the bound agent, so the exact key a
        caller can build is not always the one stored. Extensions continue after a ``:`` segment
        boundary, so ``…:peer-a`` never matches ``…:peer-ab``. The range form keeps SQLite on the
        ``channel_session_key`` index; a ``LIKE`` prefix would scan the table.
        """
        from sqlalchemy import or_, select

        from app.database.models import Chat

        lo = f"{base_key}:"
        hi = f"{base_key};"
        async with UnitOfWork() as uow:
            result = await uow.session.execute(
                select(Chat.channel_session_key)
                .where(
                    or_(
                        Chat.channel_session_key == base_key,
                        (Chat.channel_session_key >= lo) & (Chat.channel_session_key < hi),
                    )
                )
                .order_by(Chat.updated_at.desc())
                .limit(1)
            )
            row = result.first()
            if row is None:
                return None
            return await _ChatServiceBase._cr(uow).get_channel_chat_by_key(str(row[0]))

    @staticmethod
    async def get_or_create_channel_chat(
        first: str,
        second: str,
        source: str | None = None,
        *,
        agent_id: str | None = None,
    ) -> ChatDTO:
        """``get_or_create_channel_chat(session_key, source)`` or
        ``get_or_create_channel_chat(user_id, session_key, source)``.
        """
        if source is None:
            channel_session_key, src = first, second
        else:
            _, channel_session_key, src = first, second, source
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_channel_chat_by_key(channel_session_key)
            if chat:
                if agent_id and chat.agent_id != agent_id:
                    await _ChatServiceBase._cr(uow).update_chat_fields(chat.id, {"agent_id": agent_id})
                    return chat.model_copy(update={"agent_id": agent_id})
                return chat
            from sqlalchemy.exc import IntegrityError

            new_chat = ChatDTO(
                id=str(uuid4()),
                agent_id=agent_id,
                source=src,
                channel_session_key=channel_session_key,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            await _ChatServiceBase._cr(uow).add_chat(new_chat)
            try:
                sess = uow.session
                assert sess is not None
                await sess.flush()
            except IntegrityError:
                sess = uow.session
                assert sess is not None
                await sess.rollback()
                chat = await _ChatServiceBase._cr(uow).get_channel_chat_by_key(channel_session_key)
                if chat:
                    return chat
                raise
            return new_chat
