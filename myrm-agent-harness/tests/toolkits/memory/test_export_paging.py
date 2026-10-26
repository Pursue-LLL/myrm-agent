"""Export and backup read every memory of every type, however many there are.

``iter_pages_by_type`` walks vector types by the store's own cursor and relational types by
offset; ``export_all`` serializes those walks. A store that fails part-way must make the export
fail, never shrink it: a backup that silently misses rows would be worse than none.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory._internal.storage_by_type import iter_pages_by_type
from myrm_agent_harness.toolkits.memory._internal.storage_converters import episodic_to_doc, semantic_to_doc
from myrm_agent_harness.toolkits.memory._manager import MemoryManager, import_export
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
)
from myrm_agent_harness.toolkits.vector.base import FilterDict, VectorDocument
from tests.support.dense_vector_store import DenseVectorStore

CONFIG = MemoryConfig(embedding_model="test")
NAMESPACE = "agent:test"
SCOPE = MemoryScope(primary_namespace=NAMESPACE, namespaces=[NAMESPACE])


class FakeRelational:
    """Profile and rule rows served by limit/offset, as the SQL store does."""

    def __init__(self, *, profiles: Sequence[ProfileEntry] = (), rules: Sequence[ProceduralMemory] = ()) -> None:
        self.profiles = list(profiles)
        self.rules = list(rules)
        self.calls: list[tuple[str, int, int]] = []

    async def list_profiles(
        self, *, limit: int = 1000, offset: int = 0, namespaces: list[str] | None = None
    ) -> list[ProfileEntry]:
        self.calls.append(("profiles", limit, offset))
        return self.profiles[offset : offset + limit]

    async def list_rules(
        self, *, active_only: bool = True, limit: int = 1000, offset: int = 0, namespaces: list[str] | None = None
    ) -> list[ProceduralMemory]:
        self.calls.append(("rules", limit, offset))
        return self.rules[offset : offset + limit]


class FlakyStore(DenseVectorStore):
    """A store whose second page read fails."""

    async def scroll(
        self,
        collection: str,
        limit: int = 100,
        offset: str | None = None,
        filters: FilterDict | None = None,
        order_by: tuple[str, str] | None = None,
    ) -> tuple[list[VectorDocument], str | None]:
        if len(self.scroll_calls) == 1:
            raise ConnectionError("store went away")
        return await super().scroll(collection, limit, offset, filters, order_by)


def _semantic_doc(index: int, *, archived: bool = False) -> VectorDocument:
    memory = SemanticMemory(
        id=f"s{index}",
        user_id="u1",
        content=f"fact {index}",
        status=MemoryStatus.ARCHIVED if archived else MemoryStatus.ACTIVE,
        scope=SCOPE,
    )
    doc = semantic_to_doc(memory)
    doc.vector = [0.1, 0.2]
    return doc


def _store_of(count: int, *, archived: Sequence[int] = ()) -> DenseVectorStore:
    store = DenseVectorStore()
    for i in range(count):
        store.put(CONFIG.semantic_collection, _semantic_doc(i, archived=i in archived))
    return store


def _rule(index: int) -> ProceduralMemory:
    return ProceduralMemory(id=f"r{index}", content=f"rule {index}", trigger="t", action="a", source="agent_self")


async def _walk(
    memory_type: MemoryType,
    *,
    page_size: int,
    vector: DenseVectorStore | None = None,
    relational: FakeRelational | None = None,
    include_archived: bool = True,
) -> list[list[str]]:
    return [
        [m.id for m in page]
        async for page in iter_pages_by_type(
            memory_type,
            page_size=page_size,
            relational=relational,  # type: ignore[arg-type]
            vector=vector,  # type: ignore[arg-type]
            config=CONFIG,
            include_archived=include_archived,
        )
    ]


@pytest.mark.asyncio
async def test_vector_walk_follows_the_cursor_to_the_last_page() -> None:
    store = _store_of(5)

    pages = await _walk(MemoryType.SEMANTIC, page_size=2, vector=store)

    assert pages == [["s0", "s1"], ["s2", "s3"], ["s4"]]
    assert [offset for _, _, offset in store.scroll_calls] == [None, "2", "4"]


@pytest.mark.asyncio
async def test_vector_walk_of_an_exact_multiple_has_no_empty_tail() -> None:
    store = _store_of(4)

    pages = await _walk(MemoryType.SEMANTIC, page_size=2, vector=store)

    assert pages == [["s0", "s1"], ["s2", "s3"]]
    assert len(store.scroll_calls) == 2


@pytest.mark.asyncio
async def test_vector_walk_of_an_empty_collection_yields_nothing() -> None:
    assert await _walk(MemoryType.SEMANTIC, page_size=2, vector=DenseVectorStore()) == []


@pytest.mark.asyncio
async def test_vector_walk_hides_archived_memories_unless_asked() -> None:
    store = _store_of(4, archived=(1,))

    visible = await _walk(MemoryType.SEMANTIC, page_size=10, vector=store, include_archived=False)
    everything = await _walk(MemoryType.SEMANTIC, page_size=10, vector=store, include_archived=True)

    assert visible == [["s0", "s2", "s3"]]
    assert everything == [["s0", "s1", "s2", "s3"]]


@pytest.mark.asyncio
async def test_task_digest_walk_reads_only_digests_from_the_episodic_collection() -> None:
    store = DenseVectorStore()
    for i, event_type in enumerate(["task_digest", "decision", "task_digest"]):
        doc = episodic_to_doc(EpisodicMemory(id=f"e{i}", user_id="u1", content="x", event_type=event_type))
        doc.vector = [0.1]
        store.put(CONFIG.episodic_collection, doc)

    pages = await _walk(MemoryType.TASK_DIGEST, page_size=10, vector=store)

    assert pages == [["e0", "e2"]]


@pytest.mark.asyncio
async def test_a_store_failure_part_way_propagates() -> None:
    store = FlakyStore()
    for i in range(5):
        store.put(CONFIG.semantic_collection, _semantic_doc(i))

    with pytest.raises(ConnectionError):
        await _walk(MemoryType.SEMANTIC, page_size=2, vector=store)


@pytest.mark.asyncio
async def test_rules_are_read_by_offset_until_a_short_page() -> None:
    relational = FakeRelational(rules=[_rule(i) for i in range(5)])

    pages = await _walk(MemoryType.PROCEDURAL, page_size=2, relational=relational)

    assert pages == [["r0", "r1"], ["r2", "r3"], ["r4"]]
    assert [offset for _, _, offset in relational.calls] == [0, 2, 4]


@pytest.mark.asyncio
async def test_rules_of_an_exact_multiple_end_on_an_empty_read_without_yielding_it() -> None:
    relational = FakeRelational(rules=[_rule(i) for i in range(4)])

    pages = await _walk(MemoryType.PROCEDURAL, page_size=2, relational=relational)

    assert pages == [["r0", "r1"], ["r2", "r3"]]
    assert [offset for _, _, offset in relational.calls] == [0, 2, 4]


@pytest.mark.asyncio
async def test_profile_walk_stops_on_rows_read_not_rows_shown() -> None:
    """A full page that hides an internal entry must not read as the last one."""
    now = datetime.now(UTC)
    entries = [
        ProfileEntry(id=f"p{i}", key=key, value="v", created_at=now, updated_at=now)
        for i, key in enumerate(["name", "_system_flag", "timezone", "language"])
    ]
    relational = FakeRelational(profiles=entries)

    pages = await _walk(MemoryType.PROFILE, page_size=2, relational=relational)

    assert pages == [["p0"], ["p2", "p3"]]


@pytest.mark.asyncio
async def test_types_without_a_store_to_read_yield_nothing() -> None:
    assert await _walk(MemoryType.SEMANTIC, page_size=2) == []
    assert await _walk(MemoryType.PROCEDURAL, page_size=2) == []
    assert await _walk(MemoryType.CLAIM, page_size=2, relational=FakeRelational(), vector=DenseVectorStore()) == []


def _manager(vector: DenseVectorStore | None, relational: FakeRelational | None = None) -> MemoryManager:
    return MemoryManager(
        CONFIG,
        user_id="u1",
        vector=vector,  # type: ignore[arg-type]
        relational=relational,  # type: ignore[arg-type]
        fts5_searcher=AsyncMock(),
        namespaces=[NAMESPACE],
    )


@pytest.mark.asyncio
async def test_export_all_reads_past_a_single_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_export, "_EXPORT_PAGE_SIZE", 2)
    store = _store_of(5)
    relational = FakeRelational(rules=[_rule(i) for i in range(3)])

    exported = await _manager(store, relational).export_all()

    assert [row["id"] for row in exported["semantic"]] == [f"s{i}" for i in range(5)]
    assert [row["id"] for row in exported["procedural"]] == ["r0", "r1", "r2"]


@pytest.mark.asyncio
async def test_export_all_is_not_capped_at_ten_thousand_rows() -> None:
    store = _store_of(10_050)

    exported = await _manager(store).export_all()

    assert len(exported["semantic"]) == 10_050


@pytest.mark.asyncio
async def test_export_all_keeps_archived_rows_and_leaves_out_embeddings() -> None:
    store = _store_of(3, archived=(1,))

    exported = await _manager(store).export_all()

    rows = {row["id"]: row for row in exported["semantic"]}
    assert set(rows) == {"s0", "s1", "s2"}
    assert rows["s1"]["status"] == "archived"
    assert all("embedding" not in row for row in rows.values())


@pytest.mark.asyncio
async def test_export_all_lists_only_the_types_that_hold_rows() -> None:
    exported = await _manager(_store_of(1), FakeRelational()).export_all()

    assert list(exported) == ["semantic"]


@pytest.mark.asyncio
async def test_export_all_fails_when_the_store_fails_part_way(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_export, "_EXPORT_PAGE_SIZE", 2)
    store = FlakyStore()
    for i in range(5):
        store.put(CONFIG.semantic_collection, _semantic_doc(i))

    with pytest.raises(ConnectionError):
        await _manager(store).export_all()
