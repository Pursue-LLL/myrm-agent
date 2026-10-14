"""Teardown of everything a flushed, deleted or purged chat leaves behind outside its database rows.

[INPUT]
- myrm_agent_harness.runtime.context.session.session_continuity::sync_checkpoint_messages (POS: framework-neutral SSOT aligning LangGraph checkpoint threads with persisted chat history)
- myrm_agent_harness.agent.security.approval_flow::get_allowlist, reset_denial_counter (POS: session-scoped approval grants and the cross-turn denial circuit breaker)
- app.services.agent.execution_cache::close_execution_cache_for_chat_all_agents (POS: per-chat agent execution scopes)
- app.services.external_agents.runtime_pool_registry::close_external_agent_pool_for_chat (POS: per-chat external agent runtimes)
- app.core.memory::get_cascade_memory_manager (POS: memory store used for deletion cascades)
- app.services.chat.sandbox_worktree::cleanup_sandbox_worktree (POS: git worktree lifecycle of chat sandboxes)
- app.services.infra.sandbox_cleanup::cleanup_chat_workspaces (POS: storage workspace and artifact vault cleanup, one vault scan per batch)

[OUTPUT]
- clear_conversation_state: checkpoint threads, session grants and the denial counter of a chat
- clear_runtime_caches: running pools, execution scopes and in-memory working state of a chat
- clear_extract_retry_queue: pending memory-extraction retries of a chat
- forget_chat_memories: memories derived from a chat plus its retry queue
- remove_chat_files: sandbox worktrees, storage workspaces and artifact vault objects of one or many chats
- dispose_permanently_deleted_chats: all of the above, in the order a permanent delete needs

[POS]
Single definition of the per-chat teardown steps. Every way a chat can end (focus flush, soft delete,
permanent delete, empty trash, the trash and incognito auto-purges, the safe vault purge) composes the same
steps from here, so a path cannot forget one. The database rows are deleted first and are the source of truth;
each step is fail-open because a leftover is logged and recoverable while an exception would abort a deletion
that already committed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from myrm_agent_harness.agent.security.approval_flow import get_allowlist, reset_denial_counter
from myrm_agent_harness.runtime.context.session.session_continuity import sync_checkpoint_messages

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

        await sync_checkpoint_messages(get_checkpointer(), chat_id, [])
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
    _clear_working_memory(chat_id)


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


async def remove_chat_files(sandbox_dirs: Mapping[str, str | None]) -> int:
    """Remove the files the given chats produced: sandbox worktrees, storage workspaces and artifact vault objects.

    Worktrees go one by one and are removed even when they hold uncommitted edits: once a chat is gone nothing
    in the UI can reach them, so keeping them would leak disk forever. Workspaces and vault objects go in one
    batch because every vault scan reads all object metadata, so cleaning N chats separately costs N scans.

    Args:
        sandbox_dirs: Chat id mapped to the sandbox base directory of that chat (None when it has none).

    Returns:
        Number of sandbox worktrees that were removed.
    """
    worktrees_removed = 0
    for chat_id, sandbox_base_dir in sandbox_dirs.items():
        if not sandbox_base_dir:
            continue
        try:
            from app.services.chat.sandbox_worktree import cleanup_sandbox_worktree

            await cleanup_sandbox_worktree(sandbox_base_dir, chat_id, force=True)
            worktrees_removed += 1
        except Exception as exc:
            logger.warning("Sandbox worktree cleanup failed (chat=%s): %s", chat_id, exc)
    try:
        from app.services.infra.sandbox_cleanup import cleanup_chat_workspaces

        results = await cleanup_chat_workspaces(list(sandbox_dirs))
        logger.debug("Chat workspaces cleaned (chats=%d): %s", len(sandbox_dirs), results)
    except Exception as exc:
        logger.error("Chat workspace cleanup failed (chats=%d): %s", len(sandbox_dirs), exc)
    return worktrees_removed


async def dispose_permanently_deleted_chats(sandbox_dirs: Mapping[str, str | None]) -> None:
    """Tear down everything the permanently deleted chats left behind.

    Producers are stopped first so nothing re-writes state while it is erased.

    Args:
        sandbox_dirs: Chat id mapped to the sandbox base directory of that chat (None when it has none).
    """
    for chat_id in sandbox_dirs:
        await clear_runtime_caches(chat_id)
        await clear_conversation_state(chat_id)
        await forget_chat_memories(chat_id)
    await remove_chat_files(sandbox_dirs)


def _clear_working_memory(chat_id: str) -> None:
    try:
        from app.services.memory.consolidation_service import ConsolidationService

        ConsolidationService.clear_session_working_state(chat_id)
    except Exception as exc:
        logger.warning("Failed to clear session working state (chat=%s): %s", chat_id, exc)
    try:
        from myrm_agent_harness.toolkits.memory.ephemeral_delta.notify import (
            clear_ephemeral_deltas_for_session,
        )

        clear_ephemeral_deltas_for_session(chat_id)
    except Exception as exc:
        logger.warning("Failed to clear ephemeral session deltas (chat=%s): %s", chat_id, exc)
