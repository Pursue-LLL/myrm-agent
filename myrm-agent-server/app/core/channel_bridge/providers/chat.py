"""In-app chat channel — stores messages in the application database.

Replaces the old ``delivery._deliver_to_chat`` logic with a proper
Channel implementation. Stores full metadata (progressSteps, sources)
in ``Message.extra_data`` so the frontend renders the same UI as a
normal conversation.

[INPUT]
- core.channel_bridge.base::BaseChannel (POS: Channel 抽象层)
- core.channel_bridge.types::OutboundMessage (POS: 类型定义层)
- database.models::Chat, Message (POS: ORM 模型)
- database.connection::get_session (POS: 数据库连接管理)

[OUTPUT]
- ChatChannel: 应用内 Chat 推送 Channel

[POS]
应用内消息推送。将 OutboundMessage 写入 Chat + Message 表，
前端通过 getChatDetail API 加载时自动获得完整的执行步骤和引用。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from nanoid import generate as nanoid

from app.channels import OutboundMessage
from app.channels.types import ChannelCapabilities, extract_cron_context

if TYPE_CHECKING:

    class _ChatChannelBase(Protocol):
        name: str
        capabilities: ChannelCapabilities

        async def send(self, msg: OutboundMessage) -> str | None: ...
else:
    from app.channels import BaseChannel as _ChatChannelBase

logger = logging.getLogger(__name__)


class ChatChannel(_ChatChannelBase):
    """Delivers messages to the in-app chat database."""

    name = "chat"
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        buttons=True,
        quick_replies=True,
        select_menus=True,
        interactive_callback=True,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=True,
    )

    async def send(self, msg: OutboundMessage) -> str | None:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import Chat, Message

        chat_id = msg.recipient_id
        now = datetime.now(timezone.utc)

        content = self._build_content(msg)
        extra_data: dict[str, object] | None = msg.metadata if msg.metadata else None

        async with get_session() as session:
            chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()

            cron = extract_cron_context(msg)

            if not chat:
                title = f"⏰ {cron.job_name}" if cron else "Channel Message"
                chat = Chat(
                    id=chat_id,
                    title=title,
                    last_message=content[:100],
                )
                session.add(chat)
            else:
                chat.last_message = content[:100]
                chat.updated_at = now

            message_id = nanoid(size=16)
            session.add(
                Message(
                    id=message_id,
                    chat_id=chat_id,
                    role="assistant",
                    content=content,
                    extra_data=extra_data,
                    created_at=now,
                    sent_at=now,
                    sent_timezone="UTC",
                )
            )
            await session.commit()

        logger.warning("ChatChannel: delivered to chat %s", chat_id)
        return str(message_id)

    @staticmethod
    def _build_content(msg: OutboundMessage) -> str:
        """Build message content with optional status prefix."""
        parts: list[str] = []

        cron = extract_cron_context(msg)
        if cron:
            status = "✅ Success" if cron.success else "❌ Failed"
            parts.append(f"**[{cron.job_name}]** {status}\n")

        if msg.content:
            parts.append(msg.content[:4000])

        return "\n".join(parts)
