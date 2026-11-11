"""Deleted-chat fence: a writer that outlives a chat's deletion may not bring back what the deletion purged.

[INPUT]
- memory.strategies.lineage::chat_links (POS: every chat one memory derives from)
- memory.types::AnyMemory (POS: memory data models)
- toolkits.vector.base::VectorDocument (POS: a stored vector document)

[OUTPUT]
- DELETED_CHAT_REJECTION: the reason a writer gives for refusing a memory derived from a deleted chat
- close_chat: refuse writes derived from a chat for a while, as its memories are purged
- reopen_chats: accept writes derived from the given chats again, as an import brings their memories back
- is_closed: whether writes derived from a chat are refused
- derives_from_deleted_chat: whether a memory derives from a closed chat
- keep_live: the memories that derive from no closed chat
- document_derives_from_deleted_chat: whether a stored document derives from a closed chat
- keep_live_documents: the stored documents that derive from no closed chat
- clear_closed_chats: forget every closed chat

[POS]
Deleting a chat purges what it produced, but a writer that started earlier can finish later: post-turn extraction, a
consolidation cycle, a recurrence check and a correction proposal each run for seconds to minutes and persist memories
linked to the chat, and a maintenance pass that read documents before the purge writes them back after it. Closing the
chat for ``_CLOSED_FOR_SECONDS`` makes them refuse instead of bringing the purged memories back. The registry holds only
chats the memory system saw deleted, so a chat it never saw deleted is never refused, and it lives in the process: a
write that passed the fence in the instant of the purge, or one made through another process, is not covered.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.strategies.lineage import chat_links

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory
    from myrm_agent_harness.toolkits.vector.base import VectorDocument

logger = logging.getLogger(__name__)

DELETED_CHAT_REJECTION = "Not saved: the chat this memory came from was deleted."

# Longer than any writer that can still be running when a chat is deleted.
_CLOSED_FOR_SECONDS = 900.0

# (user id, chat id) -> the monotonic instant until which writes derived from the chat are refused.
_closed_until: dict[tuple[str, str], float] = {}
# Plain lock: it guards the mutations of ``_closed_until`` and is never held across an await.
_lock = threading.Lock()


def close_chat(user_id: str, chat_id: str) -> None:
    """Refuse writes derived from the chat for a while; lapsed entries are dropped on the way."""
    now = time.monotonic()
    with _lock:
        for key in [key for key, until in _closed_until.items() if until <= now]:
            del _closed_until[key]
        _closed_until[(user_id, chat_id)] = now + _CLOSED_FOR_SECONDS


def reopen_chats(user_id: str, chat_ids: Iterable[str]) -> None:
    """Accept writes derived from the chats again: the user brought their memories back on purpose."""
    with _lock:
        for chat_id in chat_ids:
            _closed_until.pop((user_id, chat_id), None)


def clear_closed_chats() -> None:
    """Forget every closed chat."""
    with _lock:
        _closed_until.clear()


def is_closed(user_id: str, chat_id: str) -> bool:
    until = _closed_until.get((user_id, chat_id))
    return until is not None and until > time.monotonic()


def derives_from_deleted_chat(user_id: str, memory: AnyMemory) -> bool:
    """Whether the memory was written from, or built from, a closed chat; nothing is closed in the common case."""
    return bool(_closed_until) and any(is_closed(user_id, chat_id) for chat_id in chat_links(memory))


def keep_live[M: AnyMemory](user_id: str, memories: Sequence[M]) -> list[M]:
    """The memories that derive from no closed chat, in their order."""
    if not _closed_until:
        return list(memories)
    live = [memory for memory in memories if not derives_from_deleted_chat(user_id, memory)]
    if len(live) < len(memories):
        logger.info("Refused %d memories derived from a deleted chat", len(memories) - len(live))
    return live


def document_derives_from_deleted_chat(document: VectorDocument) -> bool:
    """Whether a stored document was written from, or built from, a closed chat."""
    if not _closed_until:
        return False
    metadata = document.metadata
    built_from = metadata.get("source_chat_ids")
    chats = [metadata.get("source_chat_id"), *(built_from if isinstance(built_from, list) else ())]
    user_id = str(metadata.get("user_id", ""))
    return any(isinstance(chat, str) and is_closed(user_id, chat) for chat in chats)


def keep_live_documents(documents: Sequence[VectorDocument]) -> list[VectorDocument]:
    """The stored documents that derive from no closed chat, in their order.

    A pass that reads documents, works for a while and writes them back must not bring a purged one back.
    """
    live = [document for document in documents if not document_derives_from_deleted_chat(document)]
    if len(live) < len(documents):
        logger.info("Skipped %d stored documents derived from a deleted chat", len(documents) - len(live))
    return live
