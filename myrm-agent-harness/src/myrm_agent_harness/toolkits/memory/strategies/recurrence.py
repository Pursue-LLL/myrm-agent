"""Recurrence-triggered memory consolidation strategy.

[INPUT]
- memory.config::RecurrenceConfig (POS: recurrence detection configuration)
- memory.protocols.embedding::EmbeddingProtocol (POS: text to vector)
- memory.protocols.vector::VectorStoreProtocol (POS: vector storage)
- strategies.chat_fence::is_closed (POS: whether writes derived from a chat are refused)
- strategies.recurrence_signals::{is_important, is_trivial_summary} (POS: keyword rules for must-remember signals and chitchat)

[OUTPUT]
- RecurrenceDetector: Detects recurrent topics across sessions and triggers LLM consolidation.
- RecurrenceResult: Detection result with triggered flag, consolidated content and the chats it derives from.
- purge_recurrence_buffer: Deletes a user's buffer rows, or only those one chat contributed.

[POS]
Recurrence-triggered memory consolidation. Detects topics that appear repeatedly across
sessions via embedding similarity, then triggers LLM refinement to produce high-quality
long-term memories. Includes an importance-preemption bypass for safety/health/identity
signals that consolidate immediately on first occurrence. The buffer is one collection per
deployment prefix, so every row names its owner, write scope and chat: a detector reads only
the rows of its own user and scope, and deleting a chat deletes the rows (the opening words of
its sessions) and the memories that derive from it. A check that outlives its chat's deletion
buffers nothing for it and leaves the rows of deleted chats out of what it rewrites.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.protocols.embedding import EmbeddingProtocol
from myrm_agent_harness.toolkits.memory.protocols.vector import (
    FilterDict,
    VectorDocument,
    VectorStoreProtocol,
)
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import is_closed
from myrm_agent_harness.toolkits.memory.strategies.recurrence_signals import is_important, is_trivial_summary

logger = logging.getLogger(__name__)

LLMFunc = Callable[[str, str], Awaitable[str]]

_RECURRENCE_COLLECTION_SUFFIX = "_recurrence_buffer"

_CONSOLIDATION_SYSTEM_PROMPT = """\
You are a memory consolidation specialist. Given multiple conversation snippets \
where the user repeatedly discussed the same topic, synthesize a single concise \
long-term memory entry.

Rules:
- Output ONLY the consolidated memory text (1-3 sentences)
- Capture the user's actual preference/fact/habit, not the conversation context
- Use the same language as the user's messages
- Be specific and actionable (e.g. "User prefers Python for data tasks" not "User discusses programming")
- If snippets contain contradictions, use the most recent information
"""


def buffer_collection(collection_prefix: str) -> str:
    """The vector collection holding the recurrence buffer of the deployment with this prefix."""
    return f"{collection_prefix}{_RECURRENCE_COLLECTION_SUFFIX}"


async def purge_recurrence_buffer(
    vector: VectorStoreProtocol, collection_prefix: str, *, user_id: str, chat_id: str | None = None
) -> int:
    """Delete the buffer rows of ``user_id``, or only those ``chat_id`` contributed; returns how many were removed.

    The rows hold the opening words of sessions, so they go with the chat, or with all of the user's memories,
    whether or not recurrence detection is enabled now. A buffer that was never created has no rows.
    """
    filters: FilterDict = {"user_id": user_id}
    if chat_id is not None:
        filters["source_chat_id"] = chat_id
    return await vector.delete_by_filter(buffer_collection(collection_prefix), filters)


@dataclass(frozen=True, slots=True)
class RecurrenceResult:
    """Result of recurrence detection for a session.

    ``source_chat_ids`` lists every chat a consolidated memory built from several sessions derives from; it is empty
    when the memory came from the one session being checked.
    """

    triggered: bool
    consolidated_content: str | None = None
    recurrence_count: int = 0
    topic_summary: str | None = None
    source_chat_ids: tuple[str, ...] = ()


class RecurrenceDetector:
    """Detects recurrent topics across sessions and produces consolidated memories.

    Uses a dedicated vector collection as a lightweight ring buffer: each session's
    summary embedding is stored, and on each new session end, similarity search
    identifies whether the topic has appeared >= k times (recurrence threshold).
    Only the rows of ``user_id`` written in ``primary_namespace`` count: the collection is shared by
    every user and scope of the deployment.

    When triggered, an LLM call produces a refined memory from the accumulated snippets.
    """

    def __init__(
        self,
        *,
        embedding: EmbeddingProtocol,
        vector: VectorStoreProtocol,
        collection_prefix: str,
        user_id: str,
        primary_namespace: str,
        similarity_threshold: float = 0.70,
        recurrence_k: int = 4,
        buffer_capacity: int = 200,
        importance_preemption: bool = True,
        soft_deprecation: bool = True,
    ) -> None:
        self._embedding = embedding
        self._vector = vector
        self._collection = buffer_collection(collection_prefix)
        self._user_id = user_id
        self._primary_namespace = primary_namespace
        self._similarity_threshold = similarity_threshold
        self._recurrence_k = recurrence_k
        self._buffer_capacity = buffer_capacity
        self._importance_preemption = importance_preemption
        self._soft_deprecation = soft_deprecation
        self._initialized = False

    async def _ensure_collection(self) -> None:
        if self._initialized:
            return
        await self._vector.ensure_collection(
            self._collection,
            self._embedding.dimension,
            distance="cosine",
        )
        self._initialized = True

    async def check_recurrence(
        self,
        session_summary: str,
        *,
        source_chat_id: str | None,
        llm_func: LLMFunc | None = None,
    ) -> RecurrenceResult:
        """Check if this session's topic recurs across previous sessions.

        Args:
            session_summary: A concise summary of the current session's key topics.
            source_chat_id: The chat the summary came from, recorded on its buffer row so deleting the chat
                removes the row and any memory consolidated from it; ``None`` for a session without a chat.
            llm_func: Optional LLM call for consolidation (system_prompt, user_prompt) -> response.

        Returns:
            RecurrenceResult indicating whether consolidation was triggered.
        """
        if not session_summary.strip() or self._is_deleted(source_chat_id):
            return RecurrenceResult(triggered=False)

        if self._importance_preemption and is_important(session_summary):
            return RecurrenceResult(
                triggered=True,
                consolidated_content=session_summary,
                recurrence_count=1,
                topic_summary="importance_preemption",
            )

        if is_trivial_summary(session_summary):
            return RecurrenceResult(
                triggered=False,
                recurrence_count=0,
                topic_summary="trivial_filtered",
            )

        await self._ensure_collection()

        query_vec = await self._embedding.embed(session_summary)

        similar = await self._vector.search(
            self._collection,
            query_vec,
            limit=self._recurrence_k + 10,
            filters=self._scope_filter(),
            score_threshold=self._similarity_threshold,
        )

        similar_active = [r for r in similar if not r.document.metadata.get("is_deprecated")]

        recurrence_count = len(similar_active) + 1  # +1 for current session

        # Embedding and searching take time, and the chat may have been deleted meanwhile.
        if self._is_deleted(source_chat_id):
            return RecurrenceResult(triggered=False)

        doc_id = str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()
        row_metadata: dict[str, str | int | float | bool | list[str]] = {
            "created_at": now_iso,
            "is_deprecated": False,
            "user_id": self._user_id,
            "primary_namespace": self._primary_namespace,
        }
        if source_chat_id:
            row_metadata["source_chat_id"] = source_chat_id
        await self._vector.upsert(
            self._collection,
            [VectorDocument(id=doc_id, content=session_summary, vector=query_vec, metadata=row_metadata)],
        )

        await self._evict_old_entries()

        if recurrence_count < self._recurrence_k:
            return RecurrenceResult(
                triggered=False,
                recurrence_count=recurrence_count,
            )

        snippets = [r.document.content for r in similar_active if r.document.content]
        snippets.append(session_summary)

        consolidated = await self._consolidate(snippets, llm_func)

        triggered_ids = [r.document.id for r in similar_active]
        if triggered_ids:
            if self._soft_deprecation:
                # Rewriting a row of a chat deleted since the search would bring the row back.
                deprecated_docs = [
                    VectorDocument(
                        id=r.document.id,
                        content=r.document.content,
                        vector=r.document.vector,
                        metadata={
                            **r.document.metadata,
                            "is_deprecated": True,
                            "superseded_by": doc_id,
                            "deprecated_at": now_iso,
                        },
                    )
                    for r in similar_active
                    if not self._is_deleted(r.document.metadata.get("source_chat_id"))
                ]
                if deprecated_docs:
                    await self._vector.upsert(self._collection, deprecated_docs)
            else:
                await self._vector.delete(self._collection, triggered_ids)

        chat_ids = dict.fromkeys(
            chat_id
            for chat_id in (source_chat_id, *(r.document.metadata.get("source_chat_id") for r in similar_active))
            if isinstance(chat_id, str) and chat_id
        )
        return RecurrenceResult(
            triggered=True,
            consolidated_content=consolidated,
            recurrence_count=recurrence_count,
            topic_summary=session_summary[:100],
            source_chat_ids=tuple(chat_ids),
        )

    def _is_deleted(self, chat_id: object) -> bool:
        """Whether the chat named by a summary or a buffer row was deleted; a row without a chat never is."""
        return isinstance(chat_id, str) and bool(chat_id) and is_closed(self._user_id, chat_id)

    def _scope_filter(self) -> FilterDict:
        return {"user_id": self._user_id, "primary_namespace": self._primary_namespace}

    async def _consolidate(
        self,
        snippets: list[str],
        llm_func: LLMFunc | None,
    ) -> str:
        """Consolidate multiple recurrent snippets into a single memory."""
        if llm_func is None:
            return snippets[-1]

        user_prompt = "Conversation snippets about the same topic:\n\n"
        for i, s in enumerate(snippets, 1):
            user_prompt += f"[Session {i}]: {s}\n"
        user_prompt += "\nConsolidate into a single long-term memory entry:"

        try:
            return await llm_func(_CONSOLIDATION_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.warning("Recurrence consolidation LLM call failed: %s", e)
            return snippets[-1]

    async def _evict_old_entries(self) -> None:
        """Evict entries when buffer exceeds capacity to prevent unbounded growth."""
        count = await self._vector.count(self._collection)
        if count <= self._buffer_capacity:
            return

        excess = count - self._buffer_capacity
        docs, _ = await self._vector.scroll(self._collection, limit=self._buffer_capacity + excess)
        if not docs:
            return

        deprecated = [d.id for d in docs if d.metadata.get("is_deprecated")]
        if len(deprecated) >= excess:
            to_delete = deprecated[:excess]
        else:
            remaining_excess = excess - len(deprecated)
            non_deprecated = [d.id for d in docs if not d.metadata.get("is_deprecated")]
            to_delete = deprecated + non_deprecated[:remaining_excess]

        if to_delete:
            await self._vector.delete(self._collection, to_delete)
