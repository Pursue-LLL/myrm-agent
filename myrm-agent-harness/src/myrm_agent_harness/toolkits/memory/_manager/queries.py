"""MemoryManager metadata query and session count mixin module.

[INPUT]
- memory._manager.helpers::_memory_ref (POS: memory reference serializer)
- memory._manager.helpers::_rule_has_metadata (POS: whether a rule carries a metadata pair, its chat links read from the rule's own fields)
- memory._manager.model_collections::memory_collections (POS: every embedding model's collections)
- memory._manager.shared::MemoryType (POS: memory taxonomy enum)
- memory._manager.shared::Sequence (POS: collection sequence protocol)
- memory._internal.graph_cascade::drop_chat_claims (POS: deletes the claim graph a chat's digests produced)
- memory.strategies.chat_fence::close_chat (POS: refuses writes derived from a chat while its memories are purged)
- memory.strategies.recurrence::purge_recurrence_buffer (POS: deletes the recurrence buffer rows one chat contributed)

[OUTPUT]
- MemoryManagerQueriesMixin: metadata-scoped id/ref query and chat session purge helpers

[POS]
Metadata and session query mixin — extracts memory ids/refs by metadata and aggregates chat stats. A chat's
purge and its preview read the same two links, so the preview counts exactly what the purge deletes. The purge first
closes the chat to writers still running for it, then also clears the chat's rows from the recurrence buffer, which holds
the opening words of its sessions, the claim graph its task digests were compiled into, and the profile entries that
hold its working state.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory._internal.graph_cascade import drop_chat_claims
from myrm_agent_harness.toolkits.memory._manager.helpers import _memory_ref, _rule_has_metadata
from myrm_agent_harness.toolkits.memory._manager.host import MemoryManagerHost
from myrm_agent_harness.toolkits.memory._manager.model_collections import memory_collections
from myrm_agent_harness.toolkits.memory._manager.shared import (
    FilterDict,
    MemoryType,
    Sequence,
    logger,
)
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import close_chat
from myrm_agent_harness.toolkits.memory.strategies.recurrence import purge_recurrence_buffer

# The two links that tie a memory to a chat: the chat it was written from, and every chat a memory built from several
# sources derives from. Conversation memories are written from one chat and carry only the first.
_CHAT_LINKS: tuple[tuple[str, tuple[MemoryType, ...] | None], ...] = (
    ("source_chat_id", None),
    ("source_chat_ids", (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL)),
)


class MemoryManagerQueriesMixin(MemoryManagerHost):
    """Provides metadata queries and chat session aggregation for MemoryManager."""

    def _ownership_namespaces(self) -> list[str] | None:
        """Namespaces a memory must live in to be owned; ``None`` when the manager owns every scope."""
        return None if self._all_scopes else self._namespaces

    async def list_memory_ids_by_metadata(
        self,
        metadata_key: str,
        metadata_value: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
    ) -> dict[str, list[str]]:
        """List owned memory ids whose flat metadata contains an exact key/value pair.

        Memories a model switch left in a previous model's collections are listed too,
        so the ids match what ``delete_memories_by_metadata`` removes. A rule's chat links are
        fields of the rule rather than metadata entries and match by the same key names.
        """

        selected_types = tuple(
            memory_types
            or (
                MemoryType.SEMANTIC,
                MemoryType.EPISODIC,
                MemoryType.CONVERSATION,
                MemoryType.PROCEDURAL,
            )
        )
        matches: dict[str, list[str]] = {}

        if self._vector is not None:
            filters: FilterDict = {metadata_key: metadata_value}
            for memory_type, collections in (await memory_collections(self._vector, self._config)).items():
                if memory_type not in selected_types:
                    continue
                ids: dict[str, None] = {}  # insertion-ordered set: a memory counts once across collections
                for collection in collections:
                    ids.update(
                        dict.fromkeys(i for i, owned in await self._collect_vector_ids(collection, filters) if owned)
                    )
                matches[memory_type.value] = list(ids)

        if MemoryType.PROCEDURAL in selected_types and self._relational is not None:
            rule_ids: list[str] = []
            offset = 0
            while True:
                rules = await self._relational.list_rules(
                    active_only=False,
                    limit=500,
                    offset=offset,
                    namespaces=self._ownership_namespaces(),
                )
                if not rules:
                    break
                rule_ids.extend(rule.id for rule in rules if _rule_has_metadata(rule, metadata_key, metadata_value))
                offset += len(rules)
            matches[MemoryType.PROCEDURAL.value] = rule_ids

        return matches

    async def list_memory_refs_by_metadata(
        self,
        metadata_key: str,
        metadata_value: str,
        *,
        memory_types: Sequence[MemoryType] | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        """List owned memory refs and flat metadata markers for an exact metadata key/value pair."""

        selected_types = tuple(
            memory_types
            or (
                MemoryType.SEMANTIC,
                MemoryType.EPISODIC,
                MemoryType.CONVERSATION,
                MemoryType.PROCEDURAL,
            )
        )
        refs: dict[str, list[dict[str, str]]] = {}
        vector_collections: dict[MemoryType, str] = {
            MemoryType.SEMANTIC: self._config.semantic_collection,
            MemoryType.EPISODIC: self._config.episodic_collection,
            MemoryType.CONVERSATION: self._config.conversation_collection,
        }

        if self._vector is not None:
            filters: FilterDict = {metadata_key: metadata_value}
            for memory_type, collection in vector_collections.items():
                if memory_type not in selected_types:
                    continue
                refs[memory_type.value] = [
                    _memory_ref(doc.id, doc.metadata)
                    for doc in await self._collect_vector_docs(collection, filters)
                    if self._owns_vector_doc(doc)
                ]

        if MemoryType.PROCEDURAL in selected_types and self._relational is not None:
            rule_refs: list[dict[str, str]] = []
            offset = 0
            while True:
                rules = await self._relational.list_rules(
                    active_only=False,
                    limit=500,
                    offset=offset,
                    namespaces=self._ownership_namespaces(),
                )
                if not rules:
                    break
                rule_refs.extend(
                    _memory_ref(rule.id, rule.metadata)
                    for rule in rules
                    if _rule_has_metadata(rule, metadata_key, metadata_value)
                )
                offset += len(rules)
            refs[MemoryType.PROCEDURAL.value] = rule_refs

        return refs

    async def purge_by_source_chat_id(self, chat_id: str) -> dict[str, int]:
        """Cascade-delete all memories derived from a specific chat session.

        Deletes every Semantic, Episodic, Conversation, and Procedural memory linked to the chat, whether it was
        written from that chat (``source_chat_id``) or built from it among others (``source_chat_ids``), plus any
        PendingRecords linked to this chat, the profile entries it wrote as its own working state, the chat's
        recurrence buffer rows, and the claim graph compiled from its task digests (reported in no count: it is a view
        over the digests). A failing vector link is skipped with a warning and the others still run; missing vector
        collections count 0. The chat is closed first, so a writer still running for it cannot bring back what the
        purge removes.
        """
        close_chat(self._user_id, chat_id)
        # Before the digests go: their evidence is how the claims worded from them are found.
        await drop_chat_claims(self._graph, chat_id, namespaces=self._ownership_namespaces())
        counts: dict[str, int] = {}
        for key, memory_types in _CHAT_LINKS:
            try:
                deleted = await self.delete_memories_by_metadata(key, chat_id, memory_types=memory_types)
            except Exception as e:
                logger.warning("Vector cascade deletion skipped (chat=%s, link=%s): %s", chat_id, key, e)
                continue
            for memory_type, count in deleted.items():
                counts[memory_type] = counts.get(memory_type, 0) + count
        if self._vector is not None:
            try:
                await purge_recurrence_buffer(
                    self._vector, self._config.collection_prefix, user_id=self._user_id, chat_id=chat_id
                )
            except Exception as e:
                logger.warning("Recurrence buffer purge skipped (chat=%s): %s", chat_id, e)
        if self._relational is not None:
            pending_deleted = await self._relational.delete_pending_by_source_chat_id(chat_id)
            if pending_deleted:
                counts["pending"] = pending_deleted
            profiles_deleted = await self._relational.delete_profiles_by_source_chat_id(chat_id)
            if profiles_deleted:
                counts[MemoryType.PROFILE.value] = profiles_deleted
        return counts

    async def count_by_source_chat_id(self, chat_id: str) -> dict[str, int]:
        """Count memories linked to a chat session (for UI preview before deletion).

        A memory linked through both of its chat links counts once, as the purge deletes it once.
        """
        linked: dict[str, dict[str, None]] = {}
        for key, memory_types in _CHAT_LINKS:
            try:
                id_map = await self.list_memory_ids_by_metadata(key, chat_id, memory_types=memory_types)
            except Exception as e:
                logger.warning("Vector cascade count skipped (chat=%s, link=%s): %s", chat_id, key, e)
                continue
            for memory_type, ids in id_map.items():
                linked.setdefault(memory_type, {}).update(dict.fromkeys(ids))
        result = {memory_type: len(ids) for memory_type, ids in linked.items() if ids}
        if self._relational is not None:
            pending_count = await self._relational.count_pending_by_source_chat_id(chat_id)
            if pending_count:
                result["pending"] = pending_count
            profile_count = await self._relational.count_profiles_by_source_chat_id(chat_id)
            if profile_count:
                result[MemoryType.PROFILE.value] = profile_count
        return result


__all__ = ["MemoryManagerQueriesMixin"]
