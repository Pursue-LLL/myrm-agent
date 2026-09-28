"""Retry, undo, truncate, sibling switching, and rewind mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- chat_helpers::RetryResult, RegenerateResult, UndoResult, TruncateResult, RewindResult (POS: 操作结果 DTO)
- database.repositories.chat_repo::SiblingDetail (POS: 兄弟消息详情)
- services.chat.chat_title::generate_chat_title, generate_fallback_title, call_llm_for_title (POS: Chat title generation layer decoupled from turn management)

[OUTPUT]
- _ChatTurnMixin: 重试、撤销、截断、重新生成、兄弟切换、原子回滚自愈

[POS]
对话轮次操作编排层。提供消息重试、撤销、截断（编辑重发）、重新生成（含兄弟消息管理）以及物理回滚原子补偿自愈。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.database.repositories.chat_repo import SiblingDetail
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .chat_helpers import RegenerateResult, RetryResult, RewindResult, TruncateResult, UndoResult

if TYPE_CHECKING:
    from app.database.dto import _TitleModelConfig

logger = logging.getLogger(__name__)


class _ChatTurnMixin(_ChatServiceBase):
    """Retry, undo, truncate, sibling, and title generation operations."""

    @staticmethod
    async def _refresh_last_message(uow: UnitOfWork, chat_id: str) -> None:
        """Update the chat's last_message preview after message deletion."""
        remaining = await _ChatServiceBase._cr(uow).get_latest_message(chat_id)
        new_last = ""
        if remaining:
            from myrm_agent_harness.utils.text_sanitizer import (
                extract_and_strip_think_blocks,
            )

            clean_content, _ = extract_and_strip_think_blocks(remaining.content)
            new_last = clean_content[:100]
        await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, {"last_message": new_last})

    @staticmethod
    async def _sync_checkpoint_after_mutation(chat_id: str) -> None:
        from app.services.chat.session_continuity_service import sync_chat_checkpoint_from_db

        await sync_chat_checkpoint_from_db(chat_id)

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
        async with UnitOfWork() as uow:
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
            await _ChatTurnMixin._sync_checkpoint_after_mutation(chat_id)
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
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
        return RegenerateResult(success=True, query=query, sibling_group_id=group_id)

    @staticmethod
    async def switch_sibling(chat_id: str, sibling_group_id: str, target_message_id: str) -> bool:
        """Switch the active sibling in a group. Returns True on success."""
        async with UnitOfWork() as uow:
            ok = await _ChatServiceBase._cr(uow).switch_active_sibling(sibling_group_id, target_message_id)
        if ok:
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
        return ok

    @staticmethod
    async def get_sibling_info(sibling_group_id: str) -> list[SiblingDetail]:
        """Return ordered list of sibling summaries for a group."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_sibling_info(sibling_group_id)

    @staticmethod
    async def undo_last_turn(chat_id: str, user_id: str | None = None) -> UndoResult:
        async with UnitOfWork() as uow:
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
            await _ChatTurnMixin._sync_checkpoint_after_mutation(chat_id)
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
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
            await _ChatTurnMixin._sync_checkpoint_after_mutation(chat_id)
            await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
        return result

    @staticmethod
    async def rewind_to_message(chat_id: str, message_id: str, revert_files: bool = False) -> RewindResult:
        """Rewind conversation to before a user message and return composer seed text.

        When ``revert_files`` is set, file changes made by the deleted messages are
        also reverted (newest first) so the workspace matches the pre-rewind state.
        """
        from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

        from app.services.chat.session_continuity_service import (
            SessionBusyError,
            assert_session_available_for_continuity,
            pause_active_goal_for_rewind,
        )

        try:
            assert_session_available_for_continuity(chat_id)
        except SessionBusyError:
            return RewindResult(
                success=False,
                deleted_count=0,
                composer_text="",
                message_index=-1,
                goal_paused=False,
                error="SESSION_BUSY",
            )

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

            all_messages = await _ChatServiceBase._cr(uow).get_all_messages(chat_id)
            message_index = next((idx for idx, item in enumerate(all_messages) if item.id == message_id), -1)
            clean_content, _ = extract_and_strip_think_blocks(msg.content)
            composer_text = clean_content.strip()

            deleted_ids = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id,
                msg,
                include_anchor=True,
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

        await _ChatTurnMixin._sync_checkpoint_after_mutation(chat_id)
        await _ChatTurnMixin._sync_usage_after_mutation(chat_id)
        goal_paused = await pause_active_goal_for_rewind(chat_id)

        file_revert: dict[str, list[str]] = {}
        if revert_files:
            pre_snap_id = await _ChatTurnMixin._snapshot_pre_rewind(chat_id)
            try:
                file_revert = await _ChatTurnMixin._revert_files_for_messages(chat_id, deleted_ids)
            except Exception as exc:
                logger.error(
                    "Physical file revert failed for chat=%s, executing rollback compensation: %s",
                    chat_id,
                    exc,
                )
                if pre_snap_id:
                    await _ChatTurnMixin._restore_pre_rewind_snapshot(chat_id, pre_snap_id)
                raise exc
        else:
            await _ChatTurnMixin._cleanup_orphan_snapshots(chat_id, deleted_ids)

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
    async def _snapshot_pre_rewind(chat_id: str) -> str | None:
        """Take a pre-rollback workspace snapshot before a file-reverting rewind.

        Mirrors the pre-rollback protection of snapshot restore so the user can
        undo an accidental rewind from the file snapshot panel. Best-effort: a
        snapshot failure must never block the rewind itself.
        """
        from myrm_agent_harness.agent.file_snapshot import create_file_snapshot_store
        from myrm_agent_harness.agent.file_snapshot.types import SnapshotTrigger

        from app.services.chat.effective_workspace import resolve_effective_chat_workspace

        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
        if not chat:
            return None
        workspace = await resolve_effective_chat_workspace(chat, jit_fallback=False)
        if not workspace:
            return None
        try:
            store = await create_file_snapshot_store()
            return await store.take_snapshot(
                working_dir=workspace,
                trigger=SnapshotTrigger.PRE_ROLLBACK,
            )
        except Exception as e:
            logger.warning("Pre-rewind snapshot failed (chat=%s): %s", chat_id, e)
            return None

    @staticmethod
    async def _restore_pre_rewind_snapshot(chat_id: str, snapshot_id: str) -> bool:
        """Restore workspace to pre-rewind snapshot when physical file revert fails."""
        from myrm_agent_harness.agent.file_snapshot import create_file_snapshot_store

        from app.services.chat.effective_workspace import resolve_effective_chat_workspace

        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
        if not chat:
            return False
        workspace = await resolve_effective_chat_workspace(chat, jit_fallback=False)
        if not workspace:
            return False
        try:
            store = await create_file_snapshot_store()
            res = await store.restore(snapshot_id)
            return res.success
        except Exception as exc:
            logger.warning("Restoring pre-rewind snapshot failed (chat=%s): %s", chat_id, exc)
            return False

    @staticmethod
    async def _revert_files_for_messages(chat_id: str, deleted_message_ids: list[str]) -> dict[str, list[str]]:
        """Revert file changes made by deleted messages, newest message first.

        A later message may overwrite a file touched by an earlier one, so reverting
        in reverse chronological order restores each file to its state before the
        rewind target message. Messages without snapshots are skipped gracefully.
        """
        from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService

        from app.services.files.revert_agent_notify import notify_agent_of_turn_revert
        from app.services.files.revert_hydrate import (
            cleanup_persisted_snapshots,
            ensure_session_snapshots_hydrated,
        )

        await ensure_session_snapshots_hydrated(chat_id)

        reverted_files: list[str] = []
        warnings: list[str] = []
        skipped_files: list[str] = []
        for message_id in reversed(deleted_message_ids):
            result = await RevertService.revert_message(chat_id, message_id)
            if result.reverted_files:
                await cleanup_persisted_snapshots(chat_id, message_id)
                reverted_files.extend(result.reverted_files)
            warnings.extend(result.warnings)
            skipped_files.extend(result.skipped_files)

        # A file touched by multiple messages is reported by each revert; keep
        # first occurrence order so the UI count reflects distinct files.
        reverted_files = list(dict.fromkeys(reverted_files))

        if reverted_files:
            notify_agent_of_turn_revert(
                session_id=chat_id,
                message_id=None,
                reverted_files=reverted_files,
            )

        return {
            "reverted_files": reverted_files,
            "warnings": warnings,
            "skipped_files": skipped_files,
        }

    @staticmethod
    async def _cleanup_orphan_snapshots(chat_id: str, deleted_message_ids: list[str]) -> None:
        """Drop snapshot state for messages removed by a conversation-only rewind.

        File snapshots (System A) are persisted per message; when the rewind
        scope excludes files, removed messages' snapshots would otherwise stay
        on disk and be hydrated again on the next file-changes query.
        """
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            SnapshotStore,
        )

        from app.services.files.revert_hydrate import cleanup_persisted_snapshots

        store = SnapshotStore.get()
        for message_id in deleted_message_ids:
            store.remove_message(chat_id, message_id)
            await cleanup_persisted_snapshots(chat_id, message_id)

    @staticmethod
    async def generate_chat_title(
        messages: list,
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
