"""Chat trash, permanent deletion and orphan-session purge mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- chat_bound_rows::delete_trashed_chat_bound_rows (POS: 绑定会话、没有外键的行的回收站守卫删除)
- chat_disposal (POS: 会话结束后的统一拆除步骤)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)
- app.core.memory::get_cascade_memory_manager (POS: 记忆级联管理器，仅用于删除影响预览)
- app.core.infra.health.session_diagnostics (POS: 孤儿空会话诊断与清理)

[OUTPUT]
- _ChatDeletionMixin: 软删除、批量软删除、恢复、永久删除、清空回收站、回收站列表与计数、级联影响预览、孤儿空会话清理

[POS]
聊天删除生命周期编排层。软删除只把会话移入回收站并停掉运行时；永久删除与清空回收站先在事务内删除
会话行、绑定行与召回索引，提交后再交给 ``chat_disposal`` 执行统一拆除。
"""

from __future__ import annotations

import logging

from app.database.dto import ChatDTO
from app.database.repositories.uow import UnitOfWork

from . import chat_disposal
from ._base import _ChatServiceBase
from .chat_bound_rows import delete_trashed_chat_bound_rows
from .conversation_recall_index_service import ConversationRecallIndexService

logger = logging.getLogger(__name__)


class _ChatDeletionMixin(_ChatServiceBase):
    """Trash lifecycle: soft delete, restore, permanent delete, empty trash and orphan purge."""

    @staticmethod
    async def delete_chat(chat_id: str) -> bool:
        """Soft-delete a chat session (moves to trash)."""
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            ok = await repo.soft_delete_chat(chat_id)
            if not ok:
                return False
        await ConversationRecallIndexService.set_chat_excluded(chat_id, excluded=True)
        await chat_disposal.clear_runtime_caches(chat_id)
        await chat_disposal.clear_extract_retry_queue(chat_id)
        return True

    @staticmethod
    async def batch_delete(chat_ids: list[str]) -> dict[str, int]:
        """Batch soft-delete multiple chat sessions (move to trash).

        Returns a dict with 'deleted' and 'failed' counts.
        """
        deleted = 0
        failed = 0
        for chat_id in chat_ids:
            ok = await _ChatDeletionMixin.delete_chat(chat_id)
            if ok:
                deleted += 1
            else:
                failed += 1
        return {"deleted": deleted, "failed": failed}

    @staticmethod
    async def _read_sandbox_base_dir(chat_id: str) -> str | None:
        """Read the chat sandbox path in a short read-only transaction.

        Kept separate so the delete transaction stays write-only: with a
        deferred BEGIN, a prior SELECT marks the connection read-seen and
        ``factory._escalate_write_transaction`` skips the BEGIN IMMEDIATE
        upgrade, so concurrent deletes abort with SQLITE_BUSY_SNAPSHOT — a
        lock the busy_timeout PRAGMA cannot resolve.
        """
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False, include_trashed=True)
            return chat.sandbox_base_dir if chat else None

    @staticmethod
    async def permanently_delete_chat(chat_id: str) -> bool:
        """Permanently delete a trashed chat and its workspace, including derived memories."""
        sandbox_base_dir: str | None = await _ChatDeletionMixin._read_sandbox_base_dir(chat_id)
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            sess = uow.session
            assert sess is not None
            # Both deletes act only on a chat that is in the trash, so a stale trash view erases nothing.
            await delete_trashed_chat_bound_rows(sess, [chat_id])
            ok = await repo.permanently_delete_chat(chat_id)
            if ok:
                await ConversationRecallIndexService.delete_chat(sess, chat_id)

        if ok:
            await chat_disposal.dispose_permanently_deleted_chats({chat_id: sandbox_base_dir})
        return ok

    @staticmethod
    async def restore_chat(chat_id: str) -> bool:
        """Restore a trashed chat back to active."""
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            ok = await repo.restore_chat(chat_id)
            if not ok:
                return False
        await ConversationRecallIndexService.set_chat_excluded(chat_id, excluded=False)
        return True

    @staticmethod
    async def get_trashed_chats(page: int = 1, page_size: int = 20) -> tuple[list[ChatDTO], int]:
        """List trashed chats with pagination."""
        offset = (page - 1) * page_size
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_trashed_chats_paginated(offset, page_size)

    @staticmethod
    async def count_trashed_chats() -> int:
        """Return count of trashed chats (for badge display)."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).count_trashed()

    @staticmethod
    async def empty_trash() -> int:
        """Permanently delete all trashed chats and clean workspaces, including derived memories."""
        async with UnitOfWork() as uow:
            trashed, _ = await _ChatServiceBase._cr(uow).get_trashed_chats_paginated(0, 10000)
            chat_ids = [c.id for c in trashed]
            sandbox_map = {c.id: c.sandbox_base_dir for c in trashed if c.sandbox_base_dir}
        if not chat_ids:
            return 0
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            sess = uow.session
            assert sess is not None
            await delete_trashed_chat_bound_rows(sess, chat_ids)
            for cid in chat_ids:
                await ConversationRecallIndexService.delete_chat(sess, cid)
            count = await repo.empty_trash()

        await chat_disposal.dispose_permanently_deleted_chats({cid: sandbox_map.get(cid) for cid in chat_ids})
        return count

    @staticmethod
    async def get_cascade_info(chat_id: str) -> dict[str, int]:
        """Count memories linked to a chat session (for deletion preview)."""
        try:
            from app.core.memory import get_cascade_memory_manager

            manager = await get_cascade_memory_manager()
            return await manager.count_by_source_chat_id(chat_id)
        except Exception as e:
            logger.warning("Failed to get cascade info (chat=%s): %s", chat_id, e)
            return {}

    @staticmethod
    async def count_orphan_empty_sessions(older_than_minutes: int = 15) -> int:
        """Count legacy orphan sessions lacking assistant messages."""
        from app.core.infra.health.session_diagnostics import (
            count_orphan_empty_sessions,
        )

        return await count_orphan_empty_sessions(older_than_minutes=older_than_minutes)

    @staticmethod
    async def purge_orphan_empty_sessions(older_than_minutes: int = 15) -> int:
        """Purge legacy orphan sessions lacking assistant messages."""
        from app.core.infra.health.session_diagnostics import (
            purge_orphan_empty_sessions,
        )

        return await purge_orphan_empty_sessions(older_than_minutes=older_than_minutes)
