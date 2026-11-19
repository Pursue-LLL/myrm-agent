"""File side of a chat rewind: the protective snapshot, the file revert and the snapshot cleanup.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- database.repositories.uow::UnitOfWork (POS: Unit of Work 事务层)
- services.chat.effective_workspace::resolve_effective_chat_workspace (POS: Single resolution order for chat workspace directories)
- services.files.revert_hydrate::ensure_session_snapshots_hydrated, cleanup_persisted_snapshots (POS: Server-side revert snapshot disk hydrate and cleanup)
- services.files.revert_agent_notify::notify_agent_of_turn_revert (POS: Turn-level file revert Agent notification)
- myrm_agent_harness.agent.file_snapshot::create_file_snapshot_store (POS: File snapshot subsystem for workspace file versioning)
- myrm_agent_harness.agent.meta_tools.file_ops.revert_service::RevertService (POS: File revert service)
- myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer::SnapshotStore (POS: File snapshot observer)

[OUTPUT]
- snapshot_pre_rewind: workspace snapshot taken before a file-reverting rewind
- restore_pre_rewind_snapshot: put the workspace back from that snapshot when the file revert fails
- revert_files_for_messages: revert the files the removed messages changed, newest message first
- cleanup_orphan_snapshots: drop the snapshot state of the messages a conversation-only rewind removed

[POS]
The steps of a rewind that touch workspace files and snapshot state. The message-history steps (find the rows, delete
them, resync checkpoint, usage and todos) stay in ``chat_turn.py``, which calls these in the order it needs.
"""

from __future__ import annotations

import logging

from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase

logger = logging.getLogger(__name__)


async def snapshot_pre_rewind(chat_id: str) -> str | None:
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


async def restore_pre_rewind_snapshot(chat_id: str, snapshot_id: str) -> bool:
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


async def revert_files_for_messages(chat_id: str, deleted_message_ids: list[str]) -> dict[str, list[str]]:
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


async def cleanup_orphan_snapshots(chat_id: str, deleted_message_ids: list[str]) -> None:
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
