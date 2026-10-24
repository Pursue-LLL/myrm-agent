"""Teardown of everything a flushed, deleted or purged chat leaves behind outside its database rows.

[INPUT]
- myrm_agent_harness.agent.event_log.backends.file_backend::FileEventLogBackend (POS: per-session jsonl event log that keeps the full prompts and tool results of every turn)
- myrm_agent_harness.runtime.context.session.session_continuity::clear_checkpoint_threads (POS: framework-neutral SSOT dropping a chat's LangGraph checkpoint threads)
- myrm_agent_harness.agent.security.approval_flow::get_allowlist, reset_denial_counter (POS: session-scoped approval grants and the cross-turn denial circuit breaker)
- app.config.settings::get_settings (POS: location of the event log directory)
- app.services.agent.execution_cache::close_execution_cache_for_chat_all_agents (POS: per-chat agent execution scopes)
- app.services.external_agents.runtime_pool_registry::close_external_agent_pool_for_chat (POS: per-chat external agent runtimes)
- app.core.memory::get_cascade_memory_manager (POS: memory store used for deletion cascades)
- app.services.chat.sandbox_worktree::cleanup_sandbox_worktree (POS: git worktree lifecycle of chat sandboxes)
- app.services.infra.sandbox_cleanup::cleanup_chat_workspaces (POS: storage workspace and artifact vault cleanup, one vault scan per batch)

[OUTPUT]
- clear_conversation_state: checkpoint threads, session grants and the denial counter of a chat
- clear_runtime_caches: running pools, execution scopes and ephemeral session deltas of a chat
- remove_chat_event_log: the event log file of a chat
- clear_extract_retry_queue: pending memory-extraction retries of a chat
- forget_chat_memories: memories derived from a chat plus its retry queue
- ChatFilesRemoval: how many sandbox worktrees were removed and how many were kept
- remove_chat_files: sandbox worktrees (dirty ones are kept), storage workspaces and artifact vault objects of one or many chats
- dispose_permanently_deleted_chats: all of the above, in the order a permanent delete needs

[POS]
Single definition of the per-chat teardown steps. Permanent delete, empty trash and the trash and incognito
auto-purges run all of them through ``dispose_permanently_deleted_chats``; focus flush, soft delete and the
safe vault purge compose only the steps that apply to them (the purge keeps stored memories by design).
The database rows are deleted first and are the source of truth; each step is fail-open because a leftover
is logged and recoverable while an exception would abort a deletion that already committed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.security.approval_flow import get_allowlist, reset_denial_counter
from myrm_agent_harness.runtime.context.session.session_continuity import clear_checkpoint_threads

from app.config.settings import get_settings
from app.services.agent.execution_cache import close_execution_cache_for_chat_all_agents
from app.services.external_agents.runtime_pool_registry import close_external_agent_pool_for_chat

logger = logging.getLogger(__name__)

_GRANT_OWNER = "sandbox"


async def clear_conversation_state(chat_id: str) -> bool:
    """Drop the LangGraph checkpoint threads and the session-scoped approvals of a chat.

    Checkpoints are derived state (every turn rebuilds the history from the database), so a failure is
    reported through the return value instead of raised. Session grants and the denial counter are cleared
    even when the checkpoint is not, so no privilege outlives the conversation.

    Returns:
        True when every checkpoint thread alias of the chat is gone.
    """
    checkpoint_cleared = False
    try:
        from app.platform_utils import get_checkpointer

        await clear_checkpoint_threads(get_checkpointer(), chat_id)
        checkpoint_cleared = True
    except Exception as exc:
        logger.warning("Failed to clear LangGraph checkpoint threads (chat=%s): %s", chat_id, exc)

    try:
        await get_allowlist().clear_session(_GRANT_OWNER, chat_id)
        reset_denial_counter(chat_id)
    except Exception as exc:
        logger.warning("Failed to clear session allowlist/denial state (chat=%s): %s", chat_id, exc)
    return checkpoint_cleared


async def clear_runtime_caches(chat_id: str) -> None:
    """Stop what is still running for a chat and evict its in-memory state."""
    await close_external_agent_pool_for_chat(chat_id)
    await close_execution_cache_for_chat_all_agents(chat_id)
    _clear_ephemeral_deltas(chat_id)


async def remove_chat_event_log(chat_id: str) -> None:
    """Delete the event log of a chat, which keeps the full prompts and tool results of every turn.

    Fail-open: the log is also swept by age, so a leftover is logged instead of aborting the deletion.
    """
    try:
        backend = FileEventLogBackend(log_dir=Path(get_settings().database.event_log_dir), session_id=chat_id)
        if await backend.remove_session_log(chat_id):
            logger.debug("Removed event log (chat=%s)", chat_id)
    except Exception as exc:
        logger.warning("Failed to remove event log (chat=%s): %s", chat_id, exc)


async def clear_extract_retry_queue(chat_id: str) -> None:
    """Drop pending memory-extract retry work of a chat."""
    try:
        from app.services.memory.extract_retry.extract_retry_queue import clear_for_chat

        await clear_for_chat(chat_id)
    except Exception as exc:
        logger.warning("Failed to clear memory extract retry queue (chat=%s): %s", chat_id, exc)


async def forget_chat_memories(chat_id: str) -> None:
    """Cascade-delete the memories derived from a chat (Right to be Forgotten) and its retry queue."""
    try:
        from app.core.memory import get_cascade_memory_manager

        manager = await get_cascade_memory_manager()
        counts = await manager.purge_by_source_chat_id(chat_id)
        if any(counts.values()):
            logger.info("Cascade deleted memories for chat=%s: %s", chat_id, counts)
    except Exception as exc:
        logger.warning("Cascade memory deletion failed (chat=%s): %s", chat_id, exc)
    await clear_extract_retry_queue(chat_id)


@dataclass(frozen=True)
class ChatFilesRemoval:
    """What happened to the sandbox worktrees of the chats whose files were removed."""

    removed_worktrees: int = 0
    kept_worktrees: int = 0


async def remove_chat_files(sandbox_dirs: Mapping[str, str | None]) -> ChatFilesRemoval:
    """Remove the files the given chats produced: sandbox worktrees, storage workspaces and artifact vault objects.

    Worktrees go one by one in safe mode: one that still holds uncommitted edits is kept, and so is the branch of
    commits that never reached the parent branch, because the agent's work may exist nowhere else. A kept
    worktree stays in the project folder, where ``git worktree list`` shows it, for the user to merge or delete.
    Workspaces and vault objects go in one batch because every vault scan reads all object metadata, so
    cleaning N chats separately costs N scans.

    Args:
        sandbox_dirs: Chat id mapped to the sandbox base directory of that chat (None when it has none).

    Returns:
        How many sandbox worktrees were removed and how many were left in place.
    """
    removed = 0
    kept = 0
    for chat_id, sandbox_base_dir in sandbox_dirs.items():
        if not sandbox_base_dir:
            continue
        try:
            from app.services.chat.sandbox_worktree import cleanup_sandbox_worktree

            if await cleanup_sandbox_worktree(sandbox_base_dir, chat_id):
                removed += 1
            else:
                kept += 1
        except Exception as exc:
            kept += 1
            logger.warning("Sandbox worktree cleanup failed (chat=%s): %s", chat_id, exc)
    try:
        from app.services.infra.sandbox_cleanup import cleanup_chat_workspaces

        results = await cleanup_chat_workspaces(list(sandbox_dirs))
        logger.debug("Chat workspaces cleaned (chats=%d): %s", len(sandbox_dirs), results)
    except Exception as exc:
        logger.error("Chat workspace cleanup failed (chats=%d): %s", len(sandbox_dirs), exc)
    return ChatFilesRemoval(removed_worktrees=removed, kept_worktrees=kept)


async def dispose_permanently_deleted_chats(sandbox_dirs: Mapping[str, str | None]) -> None:
    """Tear down everything the permanently deleted chats left behind.

    Producers are stopped first so nothing re-writes state while it is erased.

    Args:
        sandbox_dirs: Chat id mapped to the sandbox base directory of that chat (None when it has none).
    """
    for chat_id in sandbox_dirs:
        await clear_runtime_caches(chat_id)
        await remove_chat_event_log(chat_id)
        await clear_conversation_state(chat_id)
        await forget_chat_memories(chat_id)
    await remove_chat_files(sandbox_dirs)


def _clear_ephemeral_deltas(chat_id: str) -> None:
    try:
        from myrm_agent_harness.toolkits.memory.ephemeral_delta.notify import (
            clear_ephemeral_deltas_for_session,
        )

        clear_ephemeral_deltas_for_session(chat_id)
    except Exception as exc:
        logger.warning("Failed to clear ephemeral session deltas (chat=%s): %s", chat_id, exc)
