"""Chat service shared infrastructure.

[OUTPUT]
- _ChatRepositoryPort: Structural typing shim for the chat repository.
- _ChatServiceBase: Base class providing _cr() access to the typed repository.

[POS]
Chat mixin 基础设施。定义 repository 协议和公共 _cr() 访问器，
供各 mixin 子类共享，避免重复定义。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, cast

from app.database.dto import ChatDTO, MessageDTO
from app.database.repositories.chat_message_search_repo import MessageFtsSearchRow
from app.database.repositories.chat_repo import SiblingDetail
from app.database.repositories.uow import UnitOfWork


class _ChatRepositoryPort(Protocol):
    """Structural typing shim so mypy treats bound repository methods as typed."""

    async def get_chats_paginated(
        self,
        offset: int,
        limit: int,
        source: str | None = None,
        project_id: str | None = None,
        unassigned: bool = False,
    ) -> tuple[list[ChatDTO], int]: ...

    async def get_chat_by_id(self, chat_id: str, load_messages: bool = False) -> ChatDTO | None: ...

    async def count_messages(self, chat_id: str) -> int: ...

    async def update_chat_fields(self, chat_id: str, updates: dict[str, object]) -> None: ...

    async def update_message_extra_data(self, message_id: str, extra_data: dict[str, object]) -> None: ...

    async def add_chat(self, chat: ChatDTO) -> None: ...

    async def delete_all_messages_for_chat(self, chat_id: str) -> None: ...

    async def soft_delete_all_messages_for_chat(self, chat_id: str) -> None: ...

    async def add_messages(self, messages: list[MessageDTO]) -> None: ...

    async def get_channel_chat_by_key(self, channel_session_key: str) -> ChatDTO | None: ...

    async def add_message(self, message: MessageDTO) -> None: ...

    async def get_messages_paginated(self, chat_id: str, cursor_id: str | None = None, limit: int = 10) -> list[MessageDTO]: ...

    async def get_all_messages(self, chat_id: str) -> list[MessageDTO]: ...

    async def get_message_created_at(self, message_id: str) -> datetime | None: ...

    async def get_recent_messages(
        self,
        chat_id: str,
        limit: int = 50,
        exclude_message_id: str | None = None,
        after_ts: datetime | None = None,
    ) -> list[MessageDTO]: ...

    async def search_messages_fts(
        self,
        safe_query: str,
        limit: int,
        offset: int,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[MessageFtsSearchRow], int]: ...

    async def get_last_user_message(self, chat_id: str) -> MessageDTO | None: ...

    async def delete_messages_after(self, chat_id: str, anchor: MessageDTO, include_anchor: bool = False) -> int: ...

    async def get_latest_message(self, chat_id: str) -> MessageDTO | None: ...

    async def cas_update_compaction(
        self,
        chat_id: str,
        old_before_id: str | None,
        new_summary: str,
        new_before_id: str,
    ) -> bool: ...

    async def deactivate_last_assistant_siblings(
        self,
        chat_id: str,
        last_user_msg: MessageDTO,
    ) -> tuple[str, str]: ...

    async def switch_active_sibling(
        self,
        sibling_group_id: str,
        target_message_id: str,
    ) -> bool: ...

    async def get_sibling_info(self, sibling_group_id: str) -> list[SiblingDetail]: ...

    # Pinned Threads
    async def count_pinned(self) -> int: ...
    async def get_next_pin_order(self) -> int: ...
    async def pin_chat(self, chat_id: str, pin_order: int) -> None: ...
    async def unpin_chat(self, chat_id: str) -> None: ...
    async def reorder_pinned_chats(self, items: list[tuple[str, int]]) -> None: ...

    # Trash (soft-delete)
    async def soft_delete_chat(self, chat_id: str) -> bool: ...
    async def restore_chat(self, chat_id: str) -> bool: ...
    async def get_trashed_chats_paginated(self, offset: int, limit: int) -> tuple[list[ChatDTO], int]: ...
    async def count_trashed(self) -> int: ...
    async def permanently_delete_chat(self, chat_id: str) -> bool: ...
    async def empty_trash(self) -> int: ...


class _ChatServiceBase:
    """Base providing typed repository access for all ChatService mixins."""

    @staticmethod
    def _cr(uow: UnitOfWork) -> _ChatRepositoryPort:
        return cast(_ChatRepositoryPort, uow.chat_repo)
