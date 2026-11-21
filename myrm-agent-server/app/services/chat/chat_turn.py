"""Retry, undo, truncate, sibling switching, and rewind mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- chat_helpers::RetryResult, RegenerateResult, UndoResult, TruncateResult, RewindResult (POS: 操作结果 DTO)
- database.repositories.chat_repo::SiblingDetail (POS: 兄弟消息详情)
- services.chat.chat_title::generate_chat_title, generate_fallback_title, call_llm_for_title (POS: Chat title generation layer decoupled from turn management)
- services.chat.session_continuity_service::hold_session_for_continuity, pause_active_goal_for_rewind, invalidate_chat_checkpoint (POS: Server-layer adapter for truncate/undo/retry/rewind checkpoint consistency; holds the chat while a rewind runs)
- services.chat.rewind_files::snapshot_pre_rewind, restore_pre_rewind_snapshot, revert_files_for_messages, cleanup_orphan_snapshots (POS: File side of a chat rewind: the protective snapshot, the file revert and the snapshot cleanup)

[OUTPUT]
- _ChatTurnMixin: 重试、撤销、截断、重新生成、兄弟切换、原子回滚自愈

[POS]
对话轮次操作编排层。提供消息重试、撤销、截断（编辑重发）、重新生成（含兄弟消息管理）以及物理回滚原子补偿自愈。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.database.repositories.chat_repo import SiblingDetail
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .chat_helpers import RegenerateResult, RetryResult, RewindResult, TruncateResult, UndoResult
from .rewind_files import (
    cleanup_orphan_snapshots,
    restore_pre_rewind_snapshot,
    revert_files_for_messages,
    snapshot_pre_rewind,
)

if TYPE_CHECKING:
    from app.database.dto import _TitleModelConfig

logger = logging.getLogger(__name__)


class _ChatTurnMixin(_ChatServiceBase):
    """Retry, undo, truncate, sibling, and title generation operations.

    Retry, undo and the delete step of a rewind read and then delete, and take the write lock on entry: another writer's
    commit between their read and their delete would abort the delete with SQLITE_BUSY_SNAPSHOT, and their callers (IM
    commands, the compression-exhausted path, a rewind that has already reverted files) have no way to retry. Truncate,
    regenerate and sibling switching are only called from HTTP routes and change nothing before their write, so a lost
    write fails that request and the user repeats it.
    """

    @staticmethod
    async def _refresh_last_message(uow: UnitOfWork, chat_id: str) -> None:
        """Update the chat's last_message preview after message deletion (a note about a settled task is no preview)."""
        remaining = await _ChatServiceBase._cr(uow).get_latest_message(chat_id, conversation_only=True)
        new_last = ""
        if remaining:
            from myrm_agent_harness.utils.text_sanitizer import (
                extract_and_strip_think_blocks,
            )

            clean_content, _ = extract_and_strip_think_blocks(remaining.content)
            new_last = clean_content[:100]
        await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, {"last_message": new_last})

    @staticmethod
    async def _invalidate_checkpoint_after_mutation(chat_id: str) -> None:
        from app.services.chat.session_continuity_service import invalidate_chat_checkpoint

        await invalidate_chat_checkpoint(chat_id)

    @staticmethod
    async def _sync_todos_for_active_branch(chat_id: str) -> None:
        """Align physical workspace todos.json with folded active branch state after mutations."""
        from app.services.chat.chat_todo_sync import sync_workspace_todos_for_active_branch

        await sync_workspace_todos_for_active_branch(chat_id)

    @staticmethod
    async def _sync_usage_after_mutation(chat_id: str) -> None:
        """Rebuild the Chat.total_* usage cache after message mutations.

        Deleting messages (retry/undo/truncate/rewind), deactivating siblings
        (regenerate) or switching the active sibling changes the set of active
        assistant messages; without a rebuild the Chat usage cache would keep
        counting removed messages. ``sync_chat_usage`` is best-effort, so this
        never blocks or fails the mutation itself.
        """
        from .chat_usage_sync import sync_chat_usage

        await sync_chat_usage(chat_id)

    @staticmethod
    async def retry_last_turn(chat_id: str, user_id: str | None = None) -> RetryResult:
        async with UnitOfWork(write=True) as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                return RetryResult(success=False, query="", deleted_count=0)
            last_user = await _ChatServiceBase._cr(uow).get_last_user_message(chat_id)
            if not last_user:
                return RetryResult(success=False, query="", deleted_count=0)
            deleted_ids = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id,
                last_user,
                include_anchor=False,
            )
            result = RetryResult(
                success=True,
                query=last_user.content,
                deleted_count=len(deleted_ids),
                deleted_message_ids=deleted_ids,
            )
        if result.success:
            await _ChatTurnMixin._invalidate_checkpoint_after_mutation(chat_id)
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
            await _ChatTurnMixin._sync_todos_for_active_branch(chat_id)
        return result

    @staticmethod
    async def regenerate_last_turn(chat_id: str) -> RegenerateResult:
        """Mark the last assistant responses as inactive siblings and return the original query.

        Retry deletes later messages; regenerate preserves inactive sibling
        responses so users can switch between generated versions.
        """
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                return RegenerateResult(success=False, query="", sibling_group_id="")
            last_user = await _ChatServiceBase._cr(uow).get_last_user_message(chat_id)
            if not last_user:
                return RegenerateResult(success=False, query="", sibling_group_id="")
            query, group_id = await _ChatServiceBase._cr(uow).deactivate_last_assistant_siblings(chat_id, last_user)
        await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
        await _ChatTurnMixin._sync_todos_for_active_branch(chat_id)
        return RegenerateResult(success=True, query=query, sibling_group_id=group_id)

    @staticmethod
    async def switch_sibling(chat_id: str, sibling_group_id: str, target_message_id: str) -> bool:
        """Switch the active sibling in a group. Returns True on success."""
        async with UnitOfWork() as uow:
            ok = await _ChatServiceBase._cr(uow).switch_active_sibling(sibling_group_id, target_message_id)
        if ok:
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
            await _ChatTurnMixin._sync_todos_for_active_branch(chat_id)
        return ok

    @staticmethod
    async def get_sibling_info(sibling_group_id: str) -> list[SiblingDetail]:
        """Return ordered list of sibling summaries for a group."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_sibling_info(sibling_group_id)

    @staticmethod
    async def undo_last_turn(chat_id: str, user_id: str | None = None) -> UndoResult:
        async with UnitOfWork(write=True) as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                return UndoResult(success=False, deleted_count=0)
            last_user = await _ChatServiceBase._cr(uow).get_last_user_message(chat_id)
            if not last_user:
                return UndoResult(success=True, deleted_count=0)
            deleted_ids = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id,
                last_user,
                include_anchor=True,
            )
            if deleted_ids:
                await _ChatTurnMixin._refresh_last_message(uow, chat_id)
            result = UndoResult(
                success=True,
                deleted_count=len(deleted_ids),
                deleted_message_ids=deleted_ids,
            )
        if result.success and result.deleted_count > 0:
            await _ChatTurnMixin._invalidate_checkpoint_after_mutation(chat_id)
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
            await _ChatTurnMixin._sync_todos_for_active_branch(chat_id)
        return result

    @staticmethod
    async def truncate_after_message(chat_id: str, message_id: str) -> TruncateResult:
        """Delete all messages after the specified message (inclusive).

        Used by edit-resend: truncate old messages from the DB so agent
        context stays clean when the user edits and re-sends a message.
        """
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                return TruncateResult(success=False, deleted_count=0)
            msg = await _ChatServiceBase._cr(uow).get_message_by_id(chat_id, message_id)
            if not msg:
                return TruncateResult(success=False, deleted_count=0)
            deleted_ids = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id,
                msg,
                include_anchor=True,
            )
            if deleted_ids:
                await _ChatTurnMixin._refresh_last_message(uow, chat_id)
            result = TruncateResult(success=True, deleted_count=len(deleted_ids))
        if result.success and result.deleted_count > 0:
            await _ChatTurnMixin._invalidate_checkpoint_after_mutation(chat_id)
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
            await _ChatTurnMixin._sync_todos_for_active_branch(chat_id)
        return result

    @staticmethod
    async def rewind_to_message(chat_id: str, message_id: str, revert_files: bool = False) -> RewindResult:
        """Rewind conversation to before a user message and return composer seed text.

        When ``revert_files`` is set, file changes made by the deleted messages are
        also reverted (newest first) so the workspace matches the pre-rewind state.

        The chat is held from the first step to the last, so no entry that reserves it first starts in between. A chat
        a turn holds (an IM turn included), or a draining gateway, yields ``SESSION_BUSY``. Only the rows found in the
        first step are deleted, so a message another writer adds meanwhile stays.
        """
        from app.services.chat.session_continuity_service import SessionBusyError, hold_session_for_continuity

        try:
            async with hold_session_for_continuity(chat_id):
                return await _ChatTurnMixin._rewind_held(chat_id, message_id, revert_files)
        except SessionBusyError:
            return RewindResult(
                success=False,
                deleted_count=0,
                composer_text="",
                message_index=-1,
                goal_paused=False,
                error="SESSION_BUSY",
            )

    @staticmethod
    async def _rewind_held(chat_id: str, message_id: str, revert_files: bool) -> RewindResult:
        """The rewind itself, run while the chat's session is held."""
        from app.services.chat.session_continuity_service import pause_active_goal_for_rewind

        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                return RewindResult(
                    success=False,
                    deleted_count=0,
                    composer_text="",
                    message_index=-1,
                    goal_paused=False,
                    error="CHAT_NOT_FOUND",
                )
            msg = await _ChatServiceBase._cr(uow).get_message_by_id(chat_id, message_id)
            if not msg:
                return RewindResult(
                    success=False,
                    deleted_count=0,
                    composer_text="",
                    message_index=-1,
                    goal_paused=False,
                    error="MESSAGE_NOT_FOUND",
                )
            if msg.role != "user":
                return RewindResult(
                    success=False,
                    deleted_count=0,
                    composer_text="",
                    message_index=-1,
                    goal_paused=False,
                    error="REWIND_USER_ONLY",
                )

            # The id set is read first: every later step touches only the rows in it, so a row another writer adds after
            # this step (an IM reply, the note of a settled background task) is neither reverted nor deleted. Reading the
            # active rows after the set and intersecting below keeps that true even if the two reads see different snapshots.
            rewound_ids = await _ChatServiceBase._cr(uow).message_ids_from(chat_id, msg)
            all_messages = await _ChatServiceBase._cr(uow).get_all_messages(chat_id)
            message_index = next((idx for idx, item in enumerate(all_messages) if item.id == message_id), -1)
            composer_text = msg.content.strip()

            target_messages = all_messages[message_index:] if message_index >= 0 else []
            active_rewound_ids = [m.id for m in target_messages if m.id in rewound_ids]

        if not active_rewound_ids:
            return RewindResult(
                success=False,
                deleted_count=0,
                composer_text=composer_text,
                message_index=message_index,
                goal_paused=False,
                error="NOTHING_TO_REWIND",
            )

        # Phase 1: Physical workspace revert (executed before DB message deletion)
        # Prevents split-brain data loss if file I/O fails.
        file_revert: dict[str, list[str]] = {}
        if revert_files:
            pre_snap_id = await snapshot_pre_rewind(chat_id)
            try:
                file_revert = await revert_files_for_messages(chat_id, active_rewound_ids)
            except Exception as exc:
                logger.error(
                    "Physical file revert failed for chat=%s, executing rollback compensation: %s",
                    chat_id,
                    exc,
                )
                if pre_snap_id:
                    await restore_pre_rewind_snapshot(chat_id, pre_snap_id)
                raise exc

        # Phase 2: delete the rows the first step found and refresh the chat preview in one write transaction. It takes the
        # write lock on entry: Phase 1 may already have reverted files, so another writer's commit must not abort it now.
        async with UnitOfWork(write=True) as uow:
            deleted_ids = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id,
                msg,
                include_anchor=True,
                only_ids=rewound_ids,
            )
            if deleted_ids:
                await _ChatTurnMixin._refresh_last_message(uow, chat_id)

        if not deleted_ids:
            return RewindResult(
                success=False,
                deleted_count=0,
                composer_text=composer_text,
                message_index=message_index,
                goal_paused=False,
                error="NOTHING_TO_REWIND",
            )

        await _ChatTurnMixin._invalidate_checkpoint_after_mutation(chat_id)
        await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
        await _ChatTurnMixin._sync_todos_for_active_branch(chat_id)
        goal_paused = await pause_active_goal_for_rewind(chat_id)

        if not revert_files:
            await cleanup_orphan_snapshots(chat_id, deleted_ids)

        return RewindResult(
            success=True,
            deleted_count=len(deleted_ids),
            composer_text=composer_text,
            message_index=message_index,
            goal_paused=goal_paused,
            reverted_files=file_revert.get("reverted_files"),
            file_warnings=file_revert.get("warnings"),
            skipped_files=file_revert.get("skipped_files"),
        )

    @staticmethod
    async def generate_chat_title(
        messages: Sequence[object],
        title_model: "_TitleModelConfig | None" = None,
        fallback_title_model: "_TitleModelConfig | None" = None,
    ) -> str:
        """Generate concise chat title via dedicated chat_title module."""
        from app.services.chat.chat_title import generate_chat_title as _impl_generate_title

        return await _impl_generate_title(
            messages=messages,
            title_model=title_model,
            fallback_title_model=fallback_title_model,
        )

    @staticmethod
    def _generate_fallback_title(content: str) -> str:
        from app.services.chat.chat_title import generate_fallback_title

        return generate_fallback_title(content)

    @staticmethod
    async def _call_llm_for_title(content: str, title_model: "_TitleModelConfig") -> str:
        from app.services.chat.chat_title import call_llm_for_title

        return await call_llm_for_title(content, title_model)
