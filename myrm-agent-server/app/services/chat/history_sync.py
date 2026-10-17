"""Chat history sync — does the agent's checkpoint thread still mirror the stored conversation.

[INPUT]
- app.database.repositories.chat_history_sync_repo (POS: active branch snapshot and token column)
- app.database.factory::acquire_write_lock (POS: SQLite write lock for a transaction that reads before it writes)
- app.platform_utils::get_session_factory (POS: database sessions)
- myrm_agent_harness.runtime.context.session::HistoryMode (POS: the thread ownership a turn declares to the agent loop)

[OUTPUT]
- history_digest: content-addressed digest of a stored conversation
- decide_history_mode: ``continue`` when the thread mirrors the stored conversation, otherwise ``replace``
- commit_history_sync: record that the thread mirrors the stored conversation after a completed turn

[POS]
Business half of the single-authority history rule. The agent thread keeps what the model actually saw
(tool calls and results included), so extending it keeps the provider prefix cache warm; the stored
messages stay the authority on what the user said and saw. A digest of the stored conversation is written
only when a turn completed on the thread, so a turn that failed, was cancelled, is waiting on the user, or
any change of the stored conversation the thread did not witness (undo, edit, regenerate, sibling switch,
compaction, a server-appended notice) makes the digests differ and the next turn rebuilds the thread.
Every failure here resolves to a rebuild, never to continuing a thread that may be stale.
"""

from __future__ import annotations

import hashlib
import logging

from myrm_agent_harness.runtime.context.session import HistoryMode

from app.database.factory import acquire_write_lock
from app.database.repositories.chat_history_sync_repo import ChatHistorySyncRepository, ConversationBranch
from app.platform_utils import get_session_factory

logger = logging.getLogger(__name__)

_FIELD_SEPARATOR = "\x1f"


def history_digest(branch: ConversationBranch) -> str:
    """Digest of the compacted summary and the ordered ids of the active messages.

    Stored message content never changes in place, so ids identify it; the summary has no id of its own.
    """
    summary_digest = hashlib.sha256((branch.compacted_summary or "").encode()).hexdigest()
    parts = (summary_digest, branch.compacted_before_id or "", *branch.message_ids)
    return hashlib.sha256(_FIELD_SEPARATOR.join(parts).encode()).hexdigest()


async def decide_history_mode(chat_id: str, *, exclude_message_id: str | None) -> HistoryMode:
    """``continue`` only when the stored conversation, without the turn's own user message, is what the thread held.

    Args:
        chat_id: Chat whose thread the turn runs on.
        exclude_message_id: The user message persisted for this turn; it is the turn's input, not history.
    """
    try:
        async with get_session_factory()() as db:
            branch = await ChatHistorySyncRepository.load_branch(db, chat_id, exclude_message_id=exclude_message_id)
    except Exception:
        logger.warning("History sync read failed for chat %s; the thread is rebuilt", chat_id, exc_info=True)
        return "replace"
    if branch is None or branch.stored_token is None:
        return "replace"
    return "continue" if branch.stored_token == history_digest(branch) else "replace"


async def commit_history_sync(chat_id: str, request_message_id: str) -> bool:
    """Record that the thread mirrors the stored conversation, once this turn's answer is stored.

    Returns:
        Whether the digest was written. ``False`` leaves the previous value in place; it no longer matches
        the stored conversation, so the next turn rebuilds the thread.
    """
    try:
        async with get_session_factory()() as db:
            await acquire_write_lock(db)
            if not await ChatHistorySyncRepository.has_active_answer(db, chat_id, request_message_id):
                return False
            branch = await ChatHistorySyncRepository.load_branch(db, chat_id)
            if branch is None:
                return False
            await ChatHistorySyncRepository.store_token(db, chat_id, history_digest(branch))
            await db.commit()
    except Exception:
        logger.warning("History sync commit failed for chat %s; the next turn rebuilds the thread", chat_id, exc_info=True)
        return False
    return True
