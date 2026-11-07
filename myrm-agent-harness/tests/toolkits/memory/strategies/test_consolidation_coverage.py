"""Consolidation covers every memory once, oldest first, and never skips one it could not see.

Mock stores ignore filters and ordering, so they cannot show a backlog drained across runs, a stamp that
jumps over memories a source did not return, or consolidation's own output re-entering the window. Each
case drives a real manager over SQLite and an embedded Qdrant.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

from myrm_agent_harness.toolkits.memory._internal.storage import store_episodics_batch, store_semantics_batch
from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig, MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    ConsolidationResponse,
    MergeOp,
    get_last_consolidated_at,
    run_consolidation,
    should_consolidate,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_INSIGHT_TAG
from myrm_agent_harness.toolkits.memory.strategies.consolidation_window import fetch_candidate_window
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    EpisodicMemory,
    MemoryScope,
    ProceduralMemory,
    SemanticMemory,
)
from myrm_agent_harness.toolkits.vector.base import VectorStore
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores, create_embedded_store

# Memories are seeded far in the past so the one-hour soft lock never gates a run.
BASE = datetime.now(UTC).replace(microsecond=0) - timedelta(days=30)
HORIZON = BASE + timedelta(days=1)

NewManager = Callable[..., MemoryManager]
# Memories written below a manager (not through it) carry the scope the manager would have bound.
GLOBAL = MemoryScope(primary_namespace="global", namespaces=["global"])


def at(offset_s: int) -> datetime:
    return BASE + timedelta(seconds=offset_s)


def semantic(
    content: str, offset_s: int, *, tags: list[str] | None = None, correction_of: str | None = None
) -> SemanticMemory:
    return SemanticMemory(
        content=content,
        user_id="u1",
        scope=GLOBAL,
        created_at=at(offset_s),
        tags=tags or [],
        correction_of=correction_of,
    )


def episodic(content: str, offset_s: int) -> EpisodicMemory:
    return EpisodicMemory(content=content, user_id="u1", scope=GLOBAL, created_at=at(offset_s))


class _Embedder:
    dimension = 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.5, 0.5, 0.5]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


def _llm(response: ConsolidationResponse) -> MagicMock:
    structured = AsyncMock()
    structured.ainvoke = AsyncMock(return_value=response)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def qdrant() -> AsyncIterator[VectorStore]:
    """One embedded Qdrant for the module (cold start dominates); tests isolate by collection prefix."""
    await clear_embedded_stores()
    embedded = await create_embedded_store(path=":memory:")
    try:
        yield embedded
    finally:
        await embedded.close()
        await clear_embedded_stores()


@pytest_asyncio.fixture
async def new_manager(qdrant: VectorStore, tmp_path: Path) -> AsyncIterator[NewManager]:
    """Factory of managers that share one SQLite file and one set of collections."""
    relational = SQLiteRelationalStore(str(tmp_path / "memory.db"))
    config = MemoryConfig(embedding_model="test", collection_prefix=f"cv{uuid4().hex[:8]}", blob_storage_enabled=False)

    def build(namespaces: list[str] | None = None) -> MemoryManager:
        return MemoryManager(
            config,
            user_id="u1",
            vector=qdrant,
            embedding=_Embedder(),
            relational=relational,
            namespaces=namespaces or ["global"],
            auto_warmup=False,
        )

    yield build
    await relational.close()


async def seed(manager: MemoryManager, memories: Sequence[AnyMemory]) -> None:
    vector, embedding = manager._vec()
    semantics = [m for m in memories if isinstance(m, SemanticMemory)]
    episodics = [m for m in memories if isinstance(m, EpisodicMemory)]
    if semantics:
        await store_semantics_batch(semantics, vector, manager.config, embedding, None)
    if episodics:
        await store_episodics_batch(episodics, vector, manager.config, embedding, None)


def make_episodic_unreadable(manager: MemoryManager, monkeypatch: pytest.MonkeyPatch) -> None:
    vector, _ = manager._vec()
    scroll = vector.scroll

    async def flaky(collection: str, **kwargs: object) -> object:
        if collection == manager.config.episodic_collection:
            raise RuntimeError("episodic collection unreachable")
        return await scroll(collection, **kwargs)

    monkeypatch.setattr(vector, "scroll", flaky)


async def test_a_backlog_is_drained_oldest_first_in_windows_that_cover_every_memory_once(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    memories = [semantic(f"fact {i}", i) for i in range(250)]
    await seed(manager, memories)

    windows = []
    since = None
    for _ in range(3):
        window = await fetch_candidate_window(manager, since, 100, HORIZON)
        windows.append(window)
        since = window.advance_to

    assert [len(w.memories) for w in windows] == [100, 100, 50]
    assert [m.content for w in windows for m in w.memories] == [m.content for m in memories]
    assert [w.advance_to for w in windows] == [at(99), at(199), HORIZON]


async def test_the_window_stops_where_a_source_was_cut_short_so_an_unread_memory_is_never_skipped(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    # The semantic source holds more than one window and its oldest ten are consolidation's own insights,
    # so it shows no candidate yet; its real memories lie beyond what was read. The episodic source is
    # read to its end and its memories are newer than that point.
    insights = [semantic(f"insight {i}", i, tags=[CONSOLIDATION_INSIGHT_TAG]) for i in range(1, 11)]
    real_semantic = [semantic("fact 11", 11), semantic("fact 12", 12)]
    real_episodic = [episodic(f"event {i}", i) for i in (20, 21, 22)]
    await seed(manager, [*insights, *real_semantic, *real_episodic])

    first = await fetch_candidate_window(manager, None, 10, HORIZON)
    assert first.memories == []
    assert first.advance_to == at(10)

    second = await fetch_candidate_window(manager, first.advance_to, 10, HORIZON)
    assert [m.content for m in second.memories] == ["fact 11", "fact 12", "event 20", "event 21", "event 22"]
    assert second.advance_to == HORIZON


async def test_a_memory_dated_after_the_run_never_pushes_the_stamp_past_the_run(new_manager: NewManager) -> None:
    manager = new_manager()
    day = 86_400
    await seed(manager, [semantic("ahead 1", 2 * day), semantic("ahead 2", 3 * day)])

    window = await fetch_candidate_window(manager, None, 1, HORIZON)

    # A stamp in the future is ignored by the time gates, so a drain would restart from the oldest memory.
    assert [m.content for m in window.memories] == ["ahead 1"]
    assert window.advance_to == HORIZON


async def test_consolidations_own_output_never_re_enters_the_window(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic("User likes oolong tea", 1), semantic("User enjoys oolong tea a lot", 2)
    correction = semantic("User now prefers green tea", 3, correction_of=first.id)
    await seed(manager, [first, second, correction])
    merge = MergeOp(
        source_ids=[first.id[:8], second.id[:8]],
        merged_content="The user is fond of oolong tea",
        accuracy_score=0.9,
        importance=0.8,
    )
    response = ConsolidationResponse(operations=[merge], insights=["The user is a tea drinker overall"])

    stats = await run_consolidation(manager, _llm(response), ConsolidationConfig())

    # The run wrote a merged memory, an insight and an audit event; the user's memories, including the
    # correction a user made, are all that is left to analyze.
    assert stats.merged == 1
    window = await fetch_candidate_window(manager, None, 100, datetime.now(UTC))
    assert sorted(m.content for m in window.memories) == sorted(m.content for m in (first, second, correction))


async def test_an_unreadable_source_holds_the_stamp_but_still_yields_the_other_sources(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    await seed(manager, [semantic(f"fact {i}", i) for i in range(1, 4)])
    make_episodic_unreadable(manager, monkeypatch)

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == ["fact 1", "fact 2", "fact 3"]
    assert window.advance_to is None


async def test_unreadable_rules_hold_the_stamp_but_still_yield_the_memories(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    await seed(manager, [semantic("fact", 1)])

    async def unreachable(**_: object) -> list[ProceduralMemory]:
        raise RuntimeError("rule store unreachable")

    monkeypatch.setattr(manager._rel(), "list_rules", unreachable)

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == ["fact"]
    assert window.advance_to is None


async def test_a_source_that_was_never_written_is_empty_not_unreadable(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(manager, [semantic("fact", 1)])

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == ["fact"]
    assert window.advance_to == HORIZON


async def test_a_rule_is_a_candidate_only_when_created_after_the_stamp(new_manager: NewManager) -> None:
    manager = new_manager()
    rule = ProceduralMemory(content="When: asked → Do: answer", trigger="asked", action="answer", scope=GLOBAL)
    await manager._rel().create_rule(rule)

    since_before = await fetch_candidate_window(manager, BASE, 100, HORIZON)
    since_after = await fetch_candidate_window(manager, datetime.now(UTC) + timedelta(minutes=1), 100, HORIZON)

    assert [m.content for m in since_before.memories] == ["When: asked → Do: answer"]
    assert since_after.memories == []


async def test_consecutive_runs_drain_a_backlog_and_leave_the_stamp_at_the_run_start(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    await seed(manager, [semantic(f"fact {i}", i) for i in range(250)])
    llm, config = _llm(ConsolidationResponse()), ConsolidationConfig(max_memories=100)

    analyzed, stamps = [], []
    for _ in range(3):
        analyzed.append((await run_consolidation(manager, llm, config)).input_count)
        stamps.append(await get_last_consolidated_at(manager))

    assert analyzed == [100, 100, 50]
    assert stamps[:2] == [at(99), at(199)]
    assert stamps[2] is not None
    assert abs((datetime.now(UTC) - stamps[2]).total_seconds()) < 60


async def test_a_run_that_could_not_read_a_source_leaves_the_stamp_where_it_was(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    await seed(manager, [semantic("a fact", 1), semantic("another fact", 2)])
    llm, config = _llm(ConsolidationResponse()), ConsolidationConfig()

    with monkeypatch.context() as degraded:
        make_episodic_unreadable(manager, degraded)
        stats = await run_consolidation(manager, llm, config)
    assert stats.input_count == 2
    assert await get_last_consolidated_at(manager) is None

    await run_consolidation(manager, llm, config)
    assert await get_last_consolidated_at(manager) is not None


async def test_each_owner_namespace_keeps_its_own_stamp(new_manager: NewManager) -> None:
    global_manager = new_manager(["global"])
    project_manager = new_manager(["project:p1", "global"])

    await run_consolidation(project_manager, _llm(ConsolidationResponse()), ConsolidationConfig())

    assert await get_last_consolidated_at(project_manager) is not None
    assert await get_last_consolidated_at(global_manager) is None
    assert await should_consolidate(global_manager, ConsolidationConfig()) is True
