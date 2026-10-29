"""Telegram Forum Topic methods (Bot API 6.3+).

[INPUT]  chat_id, message_thread_id, topic name and icon
[OUTPUT] TelegramForumApi
[POS] Forum Topic CRUD group of the Telegram Bot API client; ``TelegramClient`` inherits it.
"""

from __future__ import annotations

from .api_core import TelegramApiBase


class TelegramForumApi(TelegramApiBase):
    """Create, rename, close, reopen and delete topics in a Forum supergroup."""

    async def create_forum_topic(
        self,
        chat_id: int | str,
        name: str,
        *,
        icon_color: int | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> dict[str, object]:
        """``createForumTopic`` — create a topic in a Forum supergroup chat."""
        params: dict[str, object] = {"chat_id": chat_id, "name": name}
        if icon_color is not None:
            params["icon_color"] = icon_color
        if icon_custom_emoji_id is not None:
            params["icon_custom_emoji_id"] = icon_custom_emoji_id
        return await self._call("createForumTopic", json_data=params)

    async def edit_forum_topic(
        self,
        chat_id: int | str,
        message_thread_id: int,
        *,
        name: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> bool:
        """``editForumTopic`` — rename or change icon of a topic."""
        params: dict[str, object] = {
            "chat_id": chat_id,
            "message_thread_id": message_thread_id,
        }
        if name is not None:
            params["name"] = name
        if icon_custom_emoji_id is not None:
            params["icon_custom_emoji_id"] = icon_custom_emoji_id
        await self._call("editForumTopic", json_data=params)
        return True

    async def close_forum_topic(self, chat_id: int | str, message_thread_id: int) -> bool:
        """``closeForumTopic`` — close a topic (stops new messages)."""
        await self._call(
            "closeForumTopic",
            json_data={"chat_id": chat_id, "message_thread_id": message_thread_id},
        )
        return True

    async def reopen_forum_topic(self, chat_id: int | str, message_thread_id: int) -> bool:
        """``reopenForumTopic`` — reopen a closed topic."""
        await self._call(
            "reopenForumTopic",
            json_data={"chat_id": chat_id, "message_thread_id": message_thread_id},
        )
        return True

    async def delete_forum_topic(self, chat_id: int | str, message_thread_id: int) -> bool:
        """``deleteForumTopic`` — delete a topic and all its messages."""
        await self._call(
            "deleteForumTopic",
            json_data={"chat_id": chat_id, "message_thread_id": message_thread_id},
        )
        return True
