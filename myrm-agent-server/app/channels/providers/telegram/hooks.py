"""Telegram inbound hooks — /agent command, callbacks, and auto-topic routing.

Mixin providing _pre_emit_hook and related interceptors used by TelegramChannel.

[INPUT]
- channels.types::InboundMessage
- channels.i18n::get_text
- services.agent.agent_service::AgentService
- core.channel_bridge.topic_config::SqlTopicManager

[OUTPUT]
- TelegramHooksMixin: _pre_emit_hook, agent picker, auto-topic application

[POS]
Telegram pre-emit hook mixin. Intercepts /agent commands and ag: callbacks for
inline agent switching; applies auto-topic creation before inbound dispatch.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.types import InboundMessage

if TYPE_CHECKING:
    from .api import TelegramClient

logger = logging.getLogger(__name__)


class TelegramHooksMixin:
    """Mixin providing Telegram inbound pre-emit interception.

    Requires the host class to have:
    - self._client: TelegramClient
    - self._bot_username: str | None
    - self._auto_topic: bool
    - self._background_tasks, self._user_topic_map
    - self.ensure_topic_for_user, self.sync_topic_name
    """

    _client: TelegramClient
    _bot_username: str | None
    _auto_topic: bool
    _background_tasks: set[asyncio.Task[None]]
    _user_topic_map: dict[str, int]

    async def _pre_emit_hook(self, msg: InboundMessage) -> InboundMessage | None:
        """Intercept bot commands and apply auto-topic before emitting."""
        intercepted = await self._handle_agent_command(msg)
        if intercepted is None:
            return None
        return await self._apply_auto_topic(intercepted)

    async def _handle_agent_command(self, msg: InboundMessage) -> InboundMessage | None:
        """Intercept /agent command and ag: callback for inline agent switching.

        Returns None when the message was fully handled (suppressed from agent routing).
        """
        prefix = msg.metadata.get("callback_prefix")

        if prefix == "ag":
            return await self._handle_agent_callback(msg)

        content = (msg.content or "").strip().lower()
        bot_suffix = f"/agent@{self._bot_username}".lower() if self._bot_username else ""
        if content == "/agent" or (bot_suffix and content == bot_suffix):
            try:
                await self._send_agent_picker(msg)
            except Exception as exc:
                logger.warning("TelegramChannel: /agent picker failed: %s", exc)
            return None

        return msg

    async def _send_agent_picker(self, msg: InboundMessage) -> None:
        """Query available agents and send an inline keyboard picker."""
        from app.core.channel_bridge.topic_config import SqlTopicManager
        from app.services.agent.agent_service import AgentService

        agents, _ = await AgentService.get_agent_list(page=1, page_size=50)
        chat_id = msg.chat_id or msg.sender_id
        if not chat_id:
            return

        if not agents:
            await self._client.send_message(
                chat_id,
                get_text(msg, "agent_picker_no_agents"),
                message_thread_id=int(msg.thread_id) if msg.thread_id else None,
            )
            return

        topic_mgr = SqlTopicManager()
        bound_agent_id: str | None = None
        if msg.thread_id:
            ctx = await topic_mgr.resolve_topic(msg.channel, chat_id, msg.thread_id)
            if ctx and ctx.agent_id:
                bound_agent_id = ctx.agent_id
        if not bound_agent_id:
            ctx = await topic_mgr.resolve_topic(msg.channel, chat_id, None)
            if ctx and ctx.agent_id:
                bound_agent_id = ctx.agent_id

        keyboard_rows: list[list[dict[str, str]]] = []
        for agent in agents:
            label = agent.display_name or agent.id
            if agent.id == bound_agent_id:
                label = f"✅ {label}"
            keyboard_rows.append([{"text": label, "callback_data": f"ag:{agent.id}"}])

        reply_markup = {"inline_keyboard": keyboard_rows}
        await self._client.send_message(
            chat_id,
            get_text(msg, "agent_picker_select"),
            message_thread_id=int(msg.thread_id) if msg.thread_id else None,
            reply_markup=reply_markup,
        )

    async def _handle_agent_callback(self, msg: InboundMessage) -> InboundMessage | None:
        """Update picker message with confirmation, then convert to /bind."""
        agent_id = (msg.content or "").strip()
        if not agent_id:
            return msg

        origin_msg_id = msg.metadata.get("origin_message_id")
        chat_id = msg.chat_id or msg.sender_id
        if origin_msg_id and chat_id:
            try:
                from app.services.agent.agent_service import AgentService

                agent = await AgentService.get_agent_by_id(agent_id)
                name = agent.display_name if agent else agent_id
                switched_text = get_text(msg, "agent_picker_switched", name=name)
                await self._client.edit_message_text(
                    chat_id,
                    int(origin_msg_id),
                    f"<b>{switched_text}</b>",
                    reply_markup={"inline_keyboard": []},
                )
            except Exception as exc:
                logger.debug("TelegramChannel: edit picker failed: %s", exc)

        return dataclasses.replace(msg, content=f"/bind {agent_id}")

    async def _apply_auto_topic(self, msg: InboundMessage) -> InboundMessage:
        """Auto-create a Forum topic and sync name for inbound messages.

        Only triggers when auto_topic is enabled, the chat is a Forum supergroup,
        and the message has no existing thread_id. Also syncs topic name on
        subsequent messages if the user's display name has changed.
        """
        if not self._auto_topic:
            return msg

        metadata = msg.metadata or {}
        is_forum = metadata.get("is_forum", False)
        if not is_forum or not msg.is_group:
            return msg

        if msg.thread_id and msg.sender_id:
            map_key = f"{msg.chat_id}:{msg.sender_id}"
            self._user_topic_map[map_key] = int(msg.thread_id)

            if msg.sender_name:
                task = asyncio.create_task(self.sync_topic_name(msg.chat_id, int(msg.thread_id), msg.sender_name))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            return msg

        if not msg.thread_id and msg.sender_id:
            thread_id = await self.ensure_topic_for_user(
                msg.chat_id,
                msg.sender_name or "",
                msg.sender_id,
            )
            if thread_id is not None:
                return InboundMessage(
                    channel=msg.channel,
                    sender_id=msg.sender_id,
                    content=msg.content,
                    sent_at=msg.sent_at,
                    sent_timezone=msg.sent_timezone,
                    chat_id=msg.chat_id,
                    sender_name=msg.sender_name,
                    is_group=msg.is_group,
                    is_bot=msg.is_bot,
                    mentioned=msg.mentioned,
                    media=msg.media,
                    reply_to_id=msg.reply_to_id,
                    reply_to=msg.reply_to,
                    thread_id=str(thread_id),
                    metadata=metadata,
                    message_id=msg.message_id,
                )

        return msg
