"""Unit of Work — transactional boundary for cross-repository operations.

[INPUT]
- app.database.connection (POS: 数据库连接管理)
- myrm_agent_harness.backends.profiles.types::AgentProfile (POS: Agent Profile 数据类型定义)
- app.database.repositories.agent_repo::AgentRepository (POS: Agent 领域数据仓储)
- app.database.repositories.chat_repo::ChatRepository (POS: Chat 领域数据仓储)
- app.database.repositories.chat_message_search_repo::MessageFtsSearchRow (POS: 聊天消息全文检索仓储。封装消息级 FTS5 查询，并复用 Conversation Recall 的排除策略)

[OUTPUT]
- UnitOfWork: 跨领域事务管理器，封装 AsyncSession 生命周期

[POS]
Unit of Work 事务层。管理业务服务与多个仓储之间的事务一致性。
"""

import logging
from datetime import datetime
from types import TracebackType
from typing import Self, cast

from myrm_agent_harness.backends.profiles.types import AgentProfile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.database.dto import ChatDTO, MessageDTO
from app.database.repositories.agent_repo import AgentRepository
from app.database.repositories.chat_message_search_repo import MessageFtsSearchRow
from app.database.repositories.chat_repo import ChatRepository, SiblingDetail
from app.platform_utils import get_session_factory

logger = logging.getLogger(__name__)


class UnitOfWork:
    """全局工作单元模式 (Unit of Work)

    统一管理数据库会话事务与各领域仓储实例的生命周期。
    在 async with 上下文中，所有操作共享同一个会话，
    发生异常时自动回滚，正常结束时自动提交。

    使用示例:
        async with UnitOfWork() as uow:
            await uow.chat_repo.add_chat(...)
            await uow.agent_repo.update(...)
            # 自动 commit，如果有异常则自动 rollback
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self.session_factory = session_factory or get_session_factory()
        self.session: AsyncSession | None = None
        self._chat_repo: BoundChatRepository | None = None
        self._agent_repo: BoundAgentRepository | None = None

    async def __aenter__(self) -> Self:
        self.session = self.session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.session is None:
            return

        try:
            if exc_type is not None:
                await self.session.rollback()
                logger.warning(f"UoW Rollback due to {exc_type.__name__}: {exc_val}")
            else:
                await self.session.commit()
        finally:
            await self.session.close()
            self.session = None
            self._chat_repo = None
            self._agent_repo = None

    async def commit(self) -> None:
        """手动提交流程中的检查点"""
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        """手动回滚"""
        if self.session:
            await self.session.rollback()

    @property
    def chat_repo(self) -> "BoundChatRepository":
        if self.session is None:
            raise RuntimeError("UnitOfWork must be used within an async context manager")
        if self._chat_repo is None:
            self._chat_repo = BoundChatRepository(self.session)
        return self._chat_repo

    @property
    def agent_repo(self) -> "BoundAgentRepository":
        if self.session is None:
            raise RuntimeError("UnitOfWork must be used within an async context manager")
        if self._agent_repo is None:
            self._agent_repo = BoundAgentRepository(self.session)
        return self._agent_repo


class BoundChatRepository:
    """包装原始 ChatRepository，使其免于显式传递 db"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_chats_paginated(
        self,
        offset: int,
        limit: int,
        source: str | None = None,
        project_id: str | None = None,
        unassigned: bool = False,
    ) -> tuple[list[ChatDTO], int]:
        return await ChatRepository.get_chats_paginated(
            self.session,
            offset,
            limit,
            source=source,
            project_id=project_id,
            unassigned=unassigned,
        )

    async def get_chat_by_id(self, chat_id: str, load_messages: bool = False) -> ChatDTO | None:
        return await ChatRepository.get_chat_by_id(self.session, chat_id, load_messages)

    async def count_messages(self, chat_id: str) -> int:
        return await ChatRepository.count_messages(self.session, chat_id)

    async def add_chat(self, chat: ChatDTO) -> None:
        return await ChatRepository.add_chat(self.session, chat)

    async def update_chat_fields(self, chat_id: str, updates: dict[str, object]) -> None:
        return await ChatRepository.update_chat_fields(self.session, chat_id, updates)

    async def update_message_extra_data(self, message_id: str, extra_data: dict[str, object]) -> None:
        return await ChatRepository.update_message_extra_data(self.session, message_id, extra_data)

    async def get_channel_chat_by_key(self, channel_session_key: str) -> ChatDTO | None:
        return await ChatRepository.get_channel_chat_by_key(self.session, channel_session_key)

    async def add_message(self, message: MessageDTO) -> None:
        return await ChatRepository.add_message(self.session, message)

    async def add_messages(self, messages: list[MessageDTO]) -> None:
        return await ChatRepository.add_messages(self.session, messages)

    async def delete_all_messages_for_chat(self, chat_id: str) -> None:
        return await ChatRepository.delete_all_messages_for_chat(self.session, chat_id)

    async def soft_delete_all_messages_for_chat(self, chat_id: str) -> None:
        return await ChatRepository.soft_delete_all_messages_for_chat(self.session, chat_id)

    async def delete_messages_matching(self, chat_id: str, condition: ColumnElement[bool]) -> list[MessageDTO]:
        return await ChatRepository.delete_messages_matching(self.session, chat_id, condition)

    async def get_messages_paginated(self, chat_id: str, cursor_id: str | None = None, limit: int = 10) -> list[MessageDTO]:
        return await ChatRepository.get_messages_paginated(self.session, chat_id, cursor_id, limit)

    async def get_all_messages(self, chat_id: str) -> list[MessageDTO]:
        return await ChatRepository.get_all_messages(self.session, chat_id)

    async def search_messages_fts(
        self,
        safe_query: str,
        limit: int,
        offset: int,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[MessageFtsSearchRow], int]:
        return await ChatRepository.search_messages_fts(self.session, safe_query, limit, offset, since, until)

    async def get_last_user_message(self, chat_id: str) -> MessageDTO | None:
        return await ChatRepository.get_last_user_message(self.session, chat_id)

    async def delete_messages_after(self, chat_id: str, anchor: MessageDTO, include_anchor: bool = False) -> int:
        return await ChatRepository.delete_messages_after(self.session, chat_id, anchor, include_anchor)

    async def get_latest_message(self, chat_id: str) -> MessageDTO | None:
        return await ChatRepository.get_latest_message(self.session, chat_id)

    async def get_message_by_id(self, chat_id: str, message_id: str) -> MessageDTO | None:
        return await ChatRepository.get_message_by_id(self.session, chat_id, message_id)

    async def get_message_created_at(self, message_id: str) -> datetime | None:
        return await ChatRepository.get_message_created_at(self.session, message_id)

    async def get_recent_messages(
        self,
        chat_id: str,
        limit: int = 50,
        exclude_message_id: str | None = None,
        after_ts: datetime | None = None,
    ) -> list[MessageDTO]:
        return await ChatRepository.get_recent_messages(self.session, chat_id, limit, exclude_message_id, after_ts)

    async def deactivate_last_assistant_siblings(
        self,
        chat_id: str,
        last_user_msg: MessageDTO,
    ) -> tuple[str, str]:
        return await ChatRepository.deactivate_last_assistant_siblings(self.session, chat_id, last_user_msg)

    async def switch_active_sibling(
        self,
        sibling_group_id: str,
        target_message_id: str,
    ) -> bool:
        return await ChatRepository.switch_active_sibling(self.session, sibling_group_id, target_message_id)

    async def get_sibling_info(self, sibling_group_id: str) -> list[SiblingDetail]:
        return await ChatRepository.get_sibling_info(self.session, sibling_group_id)

    # ── Pinned Threads ──────────────────────────────────────────

    async def count_pinned(self) -> int:
        return await ChatRepository.count_pinned(self.session)

    async def get_next_pin_order(self) -> int:
        return await ChatRepository.get_next_pin_order(self.session)

    async def pin_chat(self, chat_id: str, pin_order: int) -> None:
        return await ChatRepository.pin_chat(self.session, chat_id, pin_order)

    async def unpin_chat(self, chat_id: str) -> None:
        return await ChatRepository.unpin_chat(self.session, chat_id)

    async def reorder_pinned_chats(self, items: list[tuple[str, int]]) -> None:
        return await ChatRepository.reorder_pinned_chats(self.session, items)

    # ── Trash (soft-delete) ──────────────────────────────────────

    async def soft_delete_chat(self, chat_id: str) -> bool:
        return await ChatRepository.soft_delete_chat(self.session, chat_id)

    async def restore_chat(self, chat_id: str) -> bool:
        return await ChatRepository.restore_chat(self.session, chat_id)

    async def get_trashed_chats_paginated(self, offset: int, limit: int) -> tuple[list[ChatDTO], int]:
        return await ChatRepository.get_trashed_chats_paginated(self.session, offset, limit)

    async def count_trashed(self) -> int:
        return await ChatRepository.count_trashed(self.session)

    async def permanently_delete_chat(self, chat_id: str) -> bool:
        return await ChatRepository.permanently_delete_chat(self.session, chat_id)

    async def empty_trash(self) -> int:
        return await ChatRepository.empty_trash(self.session)


class BoundAgentRepository:
    """包装原始 AgentRepository，使其免于显式传递 db"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_profile(self, agent_id: str) -> AgentProfile | None:
        return await AgentRepository.get_profile(self.session, agent_id)

    async def list_profiles(self) -> list[AgentProfile]:
        return cast(list[AgentProfile], await AgentRepository.list_profiles(self.session))

    async def create_profile(self, profile: AgentProfile) -> AgentProfile:
        return await AgentRepository.create_profile(self.session, profile)

    async def update_profile(self, agent_id: str, updates: dict[str, object]) -> AgentProfile | None:
        return await AgentRepository.update_profile(self.session, agent_id, updates)

    async def delete_profile(self, agent_id: str) -> bool:
        return bool(await AgentRepository.delete_profile(self.session, agent_id))
