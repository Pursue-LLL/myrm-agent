"""Per-memory-type list / count / delete helpers over the relational and vector stores.

[INPUT]
- storage_converters::{doc_to_semantic, doc_to_episodic, doc_to_conversation, _user_filter} (POS: stateless
  conversion layer)
- memory.types::{SemanticMemory, EpisodicMemory, ConversationMemory, ProceduralMemory, MemoryType} (POS: memory
  data models)

[OUTPUT]
- list_by_type, count_by_type, delete_by_type: Type-dispatched CRUD helpers used by the memory management API
- iter_pages_by_type: walks every memory of one type page by page (export and backup)

[POS]
Per-type CRUD dispatch for the storage facade; re-exported by ``storage``. Not part of the public API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory._internal.storage_converters import (
    _user_filter,
    doc_to_conversation,
    doc_to_episodic,
    doc_to_semantic,
)
from myrm_agent_harness.toolkits.memory.types import (
    ConversationMemory,
    EpisodicMemory,
    MemoryType,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig
    from myrm_agent_harness.toolkits.memory.protocols.relational import (
        RelationalStoreProtocol,
    )
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol
    from myrm_agent_harness.toolkits.vector.base import FilterDict, VectorDocument


_Listed = SemanticMemory | EpisodicMemory | ConversationMemory | ProceduralMemory

_SORT_FIELD_MAP: dict[str, str] = {
    "created_at": "_created_ts",
    "updated_at": "_updated_ts",
    "importance": "importance",
}


def _profile_memories(entries: Sequence[ProfileEntry]) -> list[_Listed]:
    """Profile entries as memories; internal ``_system_`` keys are never shown."""
    return [
        SemanticMemory(
            id=e.id,
            content=f"{e.key}: {e.value}",
            importance=0.8,
            metadata={"key": e.key, "value": str(e.value)},
            created_at=e.created_at,
            updated_at=e.updated_at,
            scope=e.scope,
        )
        for e in entries
        if not e.key.startswith("_system_")
    ]


def _vector_route(
    memory_type: MemoryType, config: MemoryConfig
) -> tuple[str, FilterDict, Callable[[VectorDocument], SemanticMemory | EpisodicMemory | ConversationMemory]] | None:
    """Collection, type filter and converter of a memory type that lives in the vector store."""
    if memory_type == MemoryType.SEMANTIC:
        return config.semantic_collection, {}, doc_to_semantic
    if memory_type == MemoryType.EPISODIC:
        return config.episodic_collection, {}, doc_to_episodic
    if memory_type == MemoryType.CONVERSATION:
        return config.conversation_collection, {}, partial(doc_to_conversation, config=config)
    if memory_type == MemoryType.TASK_DIGEST:
        return config.episodic_collection, {"event_type": MemoryType.TASK_DIGEST.value}, doc_to_episodic
    return None


async def list_by_type(
    memory_type: MemoryType,
    *,
    limit: int,
    offset: int,
    relational: RelationalStoreProtocol | None,
    vector: VectorStoreProtocol | None,
    config: MemoryConfig,
    namespaces: list[str] | None = None,
    include_archived: bool = False,
    sort_by: str | None = None,
    sort_order: str = "desc",
    tag_filter: str | None = None,
) -> list[_Listed]:
    order_by: tuple[str, str] | None = None
    if sort_by and sort_by in _SORT_FIELD_MAP:
        order_by = (_SORT_FIELD_MAP[sort_by], sort_order)

    if memory_type == MemoryType.PROFILE and relational:
        return _profile_memories(await relational.list_profiles(limit=limit, offset=offset, namespaces=namespaces))
    if memory_type == MemoryType.PROCEDURAL and relational:
        return list(await relational.list_rules(active_only=True, limit=limit, offset=offset, namespaces=namespaces))

    def _build_filters(base_filters: FilterDict) -> FilterDict:
        if tag_filter:
            base_filters["tags"] = tag_filter.lower()
        return base_filters

    async def _scroll_with_offset(
        coll: str, filters: FilterDict, *, fetch_limit: int, skip: int
    ) -> list[VectorDocument]:
        """Qdrant scroll with integer offset emulation.

        Qdrant scroll is cursor-based (point-ID), not offset-based.
        When ``order_by`` is used we fetch ``skip + fetch_limit`` items
        and discard the first ``skip`` in-memory.  Without ``order_by``
        the existing cursor-based behaviour is used (offset=None for
        first page).
        """
        if order_by is not None and skip > 0:
            docs, _ = await vector.scroll(  # type: ignore[union-attr]
                coll, limit=skip + fetch_limit, filters=filters, order_by=order_by
            )
            return docs[skip:]
        docs, _ = await vector.scroll(  # type: ignore[union-attr]
            coll, limit=fetch_limit, filters=filters, order_by=order_by
        )
        return docs

    route = _vector_route(memory_type, config) if vector else None
    if route is None:
        return []
    coll, type_filters, convert = route
    filters = _build_filters({**_user_filter(namespaces=namespaces, include_archived=include_archived), **type_filters})
    docs = await _scroll_with_offset(coll, filters, fetch_limit=limit, skip=offset)
    return [convert(d) for d in docs]


async def _offset_pages[Row](
    fetch: Callable[[int, int], Awaitable[Sequence[Row]]], page_size: int
) -> AsyncIterator[Sequence[Row]]:
    """Fetch ``page_size`` rows at a time by offset until a page comes back short."""
    offset = 0
    while True:
        rows = await fetch(page_size, offset)
        if rows:
            yield rows
        if len(rows) < page_size:
            return
        offset += page_size


async def iter_pages_by_type(
    memory_type: MemoryType,
    *,
    page_size: int,
    relational: RelationalStoreProtocol | None,
    vector: VectorStoreProtocol | None,
    config: MemoryConfig,
    namespaces: list[str] | None = None,
    include_archived: bool = False,
) -> AsyncIterator[list[_Listed]]:
    """Walk every memory of one type, one page at a time.

    Vector types follow the store's own cursor: one pass over the collection however large it
    is (offset emulation re-reads every earlier row for each page), and no point is skipped for
    lacking a sort timestamp. Relational types page by offset and stop on a short page of rows
    read, not of rows shown. A store error propagates, because a walk that stopped half-way
    must never read as a complete one.
    """
    if vector is not None and (route := _vector_route(memory_type, config)) is not None:
        coll, type_filters, convert = route
        filters = {**_user_filter(namespaces=namespaces, include_archived=include_archived), **type_filters}
        cursor: str | None = None
        while True:
            docs, cursor = await vector.scroll(coll, limit=page_size, offset=cursor, filters=filters)
            if not docs:
                return
            yield [convert(d) for d in docs]
            if cursor is None:
                return
    if relational is None:
        return
    if memory_type == MemoryType.PROFILE:
        async for entries in _offset_pages(
            lambda limit, offset: relational.list_profiles(limit=limit, offset=offset, namespaces=namespaces),
            page_size,
        ):
            if visible := _profile_memories(entries):
                yield visible
    elif memory_type == MemoryType.PROCEDURAL:
        async for rules in _offset_pages(
            lambda limit, offset: relational.list_rules(
                active_only=True, limit=limit, offset=offset, namespaces=namespaces
            ),
            page_size,
        ):
            yield list(rules)


async def count_by_type(
    memory_type: MemoryType,
    *,
    relational: RelationalStoreProtocol | None,
    vector: VectorStoreProtocol | None,
    config: MemoryConfig,
    namespaces: list[str] | None = None,
    since: datetime | None = None,
    tag_filter: str | None = None,
) -> int:
    def _apply_tag(f: FilterDict) -> FilterDict:
        if tag_filter:
            f["tags"] = tag_filter.lower()
        return f

    if memory_type == MemoryType.PROFILE and relational:
        return await relational.count_profiles(namespaces=namespaces)
    if memory_type == MemoryType.PROCEDURAL and relational:
        return await relational.count_rules(namespaces=namespaces)
    if memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC) and vector:
        coll = config.semantic_collection if memory_type == MemoryType.SEMANTIC else config.episodic_collection
        return await vector.count(coll, filters=_apply_tag(_user_filter(namespaces=namespaces, since=since)))
    if memory_type == MemoryType.CONVERSATION and vector:
        return await vector.count(
            config.conversation_collection,
            filters=_apply_tag(_user_filter(namespaces=namespaces, since=since)),
        )
    if memory_type == MemoryType.TASK_DIGEST and vector:
        filters = _apply_tag(_user_filter(namespaces=namespaces, since=since))
        filters["event_type"] = MemoryType.TASK_DIGEST.value
        return await vector.count(config.episodic_collection, filters=filters)
    return 0


async def delete_by_type(
    memory_type: MemoryType,
    *,
    relational: RelationalStoreProtocol | None,
    vector: VectorStoreProtocol | None,
    config: MemoryConfig,
    namespaces: list[str] | None = None,
) -> int:
    if memory_type == MemoryType.PROFILE and relational:
        entries = await relational.list_profiles(namespaces=namespaces)
        count = 0
        for e in entries:
            if await relational.delete_profile(e.key, namespaces=namespaces):
                count += 1
        return count
    if memory_type == MemoryType.PROCEDURAL and relational:
        count = 0
        while True:
            rules = await relational.list_rules(
                active_only=False,
                limit=500,
                offset=0,
                namespaces=namespaces,
            )
            if not rules:
                break
            for rule in rules:
                if await relational.delete_rule(rule.id):
                    count += 1
        return count
    if memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC) and vector:
        coll = config.semantic_collection if memory_type == MemoryType.SEMANTIC else config.episodic_collection
        return await vector.delete_by_filter(coll, _user_filter(namespaces=namespaces, include_archived=True))
    return 0
