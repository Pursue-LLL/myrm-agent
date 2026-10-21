"""Telegram Forum Topic management — create, rename, close, and auto-topic.

Mixin providing Forum Topic CRUD and per-user auto-topic dedup used by TelegramChannel.

[INPUT]
- telegram.api::TelegramClient, TelegramApiError

[OUTPUT]
- TelegramTopicsMixin: create/rename/close/reopen topics, ensure_topic_for_user, sync_topic_name

[POS]
Telegram Forum Topic management mixin. Auto-creates per-user topics in supergroups
with locking to prevent duplicate creation and caches topic names for sync.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .api import TelegramApiError

if TYPE_CHECKING:
    from .api import TelegramClient

logger = logging.getLogger(__name__)


class TelegramTopicsMixin:
    """Mixin providing Telegram Forum Topic lifecycle helpers.

    Requires the host class to have:
    - self._client: TelegramClient
    - self._auto_topic: bool
    - self._topic_locks, self._topic_name_cache, self._user_topic_map
    """

    _client: TelegramClient
    _auto_topic: bool
    _topic_locks: dict[str, asyncio.Lock]
    _topic_name_cache: dict[str, str]
    _user_topic_map: dict[str, int]

    async def create_topic(
        self,
        chat_id: str,
        name: str,
        *,
        icon_color: int | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> int | None:
        """Create a Forum topic. Returns the message_thread_id or None on failure."""
        try:
            result = await self._client.create_forum_topic(
                chat_id,
                name,
                icon_color=icon_color,
                icon_custom_emoji_id=icon_custom_emoji_id,
            )
            thread_id = result.get("message_thread_id")
            if isinstance(thread_id, int):
                self._topic_name_cache[f"{chat_id}:{thread_id}"] = name
                return thread_id
            return None
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: create_topic failed: %s", exc)
            return None

    async def rename_topic(self, chat_id: str, message_thread_id: int, name: str) -> bool:
        """Rename a Forum topic."""
        try:
            result = await self._client.edit_forum_topic(chat_id, message_thread_id, name=name)
            if result:
                self._topic_name_cache[f"{chat_id}:{message_thread_id}"] = name
            return result
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: rename_topic failed: %s", exc)
            return False

    async def close_topic(self, chat_id: str, message_thread_id: int) -> bool:
        """Close a Forum topic (stops new messages from non-admins)."""
        try:
            return await self._client.close_forum_topic(chat_id, message_thread_id)
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: close_topic failed: %s", exc)
            return False

    async def reopen_topic(self, chat_id: str, message_thread_id: int) -> bool:
        """Reopen a previously closed Forum topic."""
        try:
            return await self._client.reopen_forum_topic(chat_id, message_thread_id)
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: reopen_topic failed: %s", exc)
            return False

    async def ensure_topic_for_user(
        self,
        chat_id: str,
        sender_name: str,
        sender_id: str,
    ) -> int | None:
        """Auto-create a Forum topic for a user, or reuse an existing one.

        Maintains a sender->topic mapping to prevent duplicate topic creation.
        Uses per-user locking to prevent concurrent race conditions.
        Returns the message_thread_id of the existing or newly created topic,
        or None if auto_topic is disabled or creation failed.
        """
        if not self._auto_topic:
            return None

        map_key = f"{chat_id}:{sender_id}"
        existing = self._user_topic_map.get(map_key)
        if existing is not None:
            return existing

        if map_key not in self._topic_locks:
            self._topic_locks[map_key] = asyncio.Lock()

        async with self._topic_locks[map_key]:
            existing = self._user_topic_map.get(map_key)
            if existing is not None:
                return existing

            thread_id = await self.create_topic(chat_id, sender_name or f"User {sender_id}")
            if thread_id is not None:
                self._user_topic_map[map_key] = thread_id
            return thread_id

    async def sync_topic_name(
        self,
        chat_id: str,
        message_thread_id: int,
        current_name: str,
    ) -> None:
        """Sync the Forum topic name if the user's display name has changed.

        Only calls editForumTopic when the cached name differs from the current
        display name to avoid unnecessary API calls.
        """
        if not self._auto_topic:
            return

        cache_key = f"{chat_id}:{message_thread_id}"
        cached = self._topic_name_cache.get(cache_key)
        if cached == current_name:
            return

        if await self.rename_topic(chat_id, message_thread_id, current_name):
            logger.info(
                "TelegramChannel: synced topic name %s -> %s in chat %s",
                cached,
                current_name,
                chat_id,
            )
