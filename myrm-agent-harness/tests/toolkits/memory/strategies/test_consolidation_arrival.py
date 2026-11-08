"""Consolidation analyzes memories in the order they reached the store, whatever time they carry.

A cursor over ``created_at`` loses every memory that arrives behind it: one approved after a run keeps the
time it was proposed, an import keeps its source's timestamps, and a batch can share one instant that a
window's cut falls inside. A write that is still being persisted when a run reads is invisible to it, and a
cursor that moves on would never see it again. Each case drives a real manager over SQLite and an embedded
Qdrant through the path a write takes, so the stamp is whatever the store gave it.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory._internal import store_stamp
from myrm_agent_harness.toolkits.memory._internal.storage import store_semantics_batch
from myrm_agent_harness.toolkits.memory._internal.store_stamp import STORED_TS_KEY, settled_through
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation_window import CandidateWindow, fetch_candidate_window
from myrm_agent_harness.toolkits.memory.types import ProceduralMemory, SemanticMemory
from tests.support.consolidation_seeds import NewManager, at, seed, semantic

_VECTOR = [1.0, 0.5, 0.5, 0.5]


class _GatedEmbedder:
    """Embeds at once until ``hold`` is set, then keeps every call inside the write until ``release`` is set."""

    dimension = 4

    def __init__(self) -> None:
        self.hold = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, text: str) -> list[float]:
        if self.hold:
            self.entered.set()
            await self.release.wait()
        return _VECTOR

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


class _FailingEmbedder:
    dimension = 4

    async def embed(self, text: str) -> list[float]:
        raise RuntimeError("embedding service unreachable")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding service unreachable")


class _JitterEmbedder:
    """Takes a different short time per call, so concurrent writes finish in an order of their own."""

    dimension = 4

    def __init__(self) -> None:
        self._random = random.Random(7)

    async def embed(self, text: str) -> list[float]:
        await asyncio.sleep(self._random.random() * 0.2)
        return _VECTOR

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


async def _next_window(manager: MemoryManager, since: datetime | None, max_count: int = 100) -> CandidateWindow:
    return await fetch_candidate_window(manager, since, max_count, settled_through())


def _contents(window: CandidateWindow) -> list[str]:
    return [m.content for m in window.memories]


async def test_a_memory_approved_after_a_run_is_analyzed_by_the_next_run(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    await seed(manager, [semantic("settled fact", 1)])
    # The proposal keeps the time it was made while it waits for a reviewer.
    proposal = await manager.store(SemanticMemory(content="User prefers oolong tea", created_at=at(5)))
    pending_id = str(proposal.metadata["_pending_id"])
    first = await _next_window(manager, None)
    assert _contents(first) == ["settled fact"]

    approved = await manager.approve(pending_id)

    assert approved is not None
    assert approved.created_at == at(5)
    second = await _next_window(manager, first.advance_to)
    assert _contents(second) == ["User prefers oolong tea"]


async def test_memories_imported_with_their_source_timestamps_are_analyzed(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(manager, [semantic("settled fact", 1)])
    first = await _next_window(manager, None)
    year = timedelta(days=365)
    imported = [SemanticMemory(content=f"imported {i}", created_at=at(0) - year * i) for i in range(3)]

    await manager.store_batch(imported, _bypass_approval=True, _skip_dedup=True)

    second = await _next_window(manager, first.advance_to)
    assert sorted(_contents(second)) == [f"imported {i}" for i in range(3)]


async def test_a_batch_sharing_one_creation_time_is_covered_whole_across_windows(new_manager: NewManager) -> None:
    manager = new_manager()
    batch = [SemanticMemory(content=f"fact {i:03d}", created_at=at(7)) for i in range(150)]
    await manager.store_batch(batch, _bypass_approval=True, _skip_dedup=True)

    windows: list[CandidateWindow] = []
    since: datetime | None = None
    for _ in range(2):
        window = await _next_window(manager, since, max_count=100)
        windows.append(window)
        since = window.advance_to

    # The cut falls between memories that carry the same instant; the stamp tells them apart.
    assert [len(w.memories) for w in windows] == [100, 50]
    assert sorted(m.content for w in windows for m in w.memories) == [m.content for m in batch]


async def test_a_write_still_being_persisted_is_left_for_the_next_run(new_manager: NewManager) -> None:
    gated = _GatedEmbedder()
    manager = new_manager(embedding=gated)
    await seed(manager, [semantic("settled fact", 1)])
    gated.hold = True
    slow = SemanticMemory(content="slow write")
    writing = asyncio.create_task(manager.store(slow, _bypass_approval=True))
    await asyncio.wait_for(gated.entered.wait(), timeout=10)

    during = await _next_window(manager, None)
    gated.release.set()
    stored = await writing

    assert _contents(during) == ["settled fact"]
    assert during.advance_to is not None
    assert stored.stored_at is not None
    assert during.advance_to < stored.stored_at
    after = await _next_window(manager, during.advance_to)
    assert _contents(after) == ["slow write"]


async def test_a_write_that_fails_does_not_hold_the_stamp(new_manager: NewManager) -> None:
    manager = new_manager(embedding=_FailingEmbedder())
    doomed = SemanticMemory(content="never stored")

    with pytest.raises(RuntimeError, match="embedding service unreachable"):
        await manager.store(doomed, _bypass_approval=True)

    assert doomed.stored_at is not None
    assert settled_through() > doomed.stored_at


async def test_a_write_that_is_cancelled_does_not_hold_the_stamp(new_manager: NewManager) -> None:
    gated = _GatedEmbedder()
    manager = new_manager(embedding=gated)
    gated.hold = True
    abandoned = SemanticMemory(content="abandoned write")
    writing = asyncio.create_task(manager.store(abandoned, _bypass_approval=True))
    await asyncio.wait_for(gated.entered.wait(), timeout=10)

    writing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await writing

    assert abandoned.stored_at is not None
    assert settled_through() > abandoned.stored_at


async def test_no_memory_is_skipped_while_writes_finish_in_a_different_order(new_manager: NewManager) -> None:
    manager = new_manager(embedding=_JitterEmbedder())
    # The collection exists before the writers race: creating it is not what this case is about.
    await seed(manager, [semantic("settled fact", 1)])
    memories = [SemanticMemory(content=f"fact {i:02d}") for i in range(40)]
    writers = asyncio.gather(*(manager.store(m, _bypass_approval=True) for m in memories))

    seen: list[str] = []
    since: datetime | None = None
    while not writers.done():
        window = await _next_window(manager, since, max_count=7)
        seen.extend(_contents(window))
        since = window.advance_to if window.advance_to is not None else since
        await asyncio.sleep(0.001)
    await writers
    while True:
        window = await _next_window(manager, since, max_count=7)
        seen.extend(_contents(window))
        since = window.advance_to
        if not window.memories:
            break

    assert sorted(seen) == sorted(["settled fact", *(m.content for m in memories)])


async def test_rewriting_a_memory_keeps_the_arrival_it_was_stored_with(new_manager: NewManager) -> None:
    manager = new_manager()
    stored = await manager.store(SemanticMemory(content="User likes tea"), _bypass_approval=True)

    rewritten = await manager.update_memory(stored.id, content="User likes oolong tea")

    assert rewritten.stored_at == stored.stored_at
    window = await _next_window(manager, None)
    assert [(m.content, m.stored_at) for m in window.memories] == [("User likes oolong tea", stored.stored_at)]


async def test_the_store_stamps_every_memory_whatever_stamp_the_caller_sets(new_manager: NewManager) -> None:
    manager = new_manager()
    claimed = SemanticMemory(content="claims to be old", stored_at=datetime(2001, 1, 1, tzinfo=UTC))

    stored = await manager.store(claimed, _bypass_approval=True)

    assert stored.stored_at is not None
    assert stored.stored_at > datetime.now(UTC) - timedelta(minutes=5)
    vector, _ = manager._vec()
    [document] = await vector.get(manager.config.semantic_collection, [stored.id])
    assert document.metadata[STORED_TS_KEY] == stored.stored_at.timestamp()


async def test_rules_and_memories_are_analyzed_in_the_order_they_arrived(new_manager: NewManager) -> None:
    manager = new_manager()
    await manager.store(SemanticMemory(content="fact before"), _bypass_approval=True)
    await manager.store(
        ProceduralMemory(content="When: asked → Do: answer", trigger="asked", action="answer"), _bypass_approval=True
    )
    await manager.store(SemanticMemory(content="fact after"), _bypass_approval=True)

    window = await _next_window(manager, None)

    assert _contents(window) == ["fact before", "When: asked → Do: answer", "fact after"]


async def test_a_rule_stored_while_the_stamp_clock_leads_the_wall_clock_is_still_analyzed(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    # A wall clock that steps back leaves the stamp clock ahead of it until the wall clock catches up.
    monkeypatch.setattr(store_stamp, "_last_stamp_us", time.time_ns() // 1000 + 60_000_000)
    covered = await _next_window(manager, None)
    await manager.store(
        ProceduralMemory(content="When: later → Do: act", trigger="later", action="act"), _bypass_approval=True
    )

    window = await _next_window(manager, covered.advance_to)

    assert _contents(window) == ["When: later → Do: act"]


async def test_documents_stored_before_stamps_existed_are_stamped_from_their_creation_time(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    vector, embedding = manager._vec()
    legacy = [semantic(f"legacy {i}", i) for i in range(1, 4)]
    for memory in legacy:
        memory.stored_at = None
    await store_semantics_batch(legacy, vector, manager.config, embedding, None)
    collection = manager.config.semantic_collection
    unseen, _ = await vector.scroll(collection, limit=10, order_by=(STORED_TS_KEY, "asc"))
    assert unseen == []

    window = await fetch_candidate_window(manager, None, 100, at(10))

    assert _contents(window) == ["legacy 1", "legacy 2", "legacy 3"]
    documents = await vector.get(collection, [m.id for m in legacy])
    assert sorted(d.metadata[STORED_TS_KEY] for d in documents) == [at(i).timestamp() for i in (1, 2, 3)]
    assert await vector.backfill_payload_copy(collection, STORED_TS_KEY, "_created_ts") == 0
    later = await fetch_candidate_window(manager, at(1), 100, at(10))
    assert _contents(later) == ["legacy 2", "legacy 3"]
