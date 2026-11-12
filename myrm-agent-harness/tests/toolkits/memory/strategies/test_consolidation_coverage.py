"""Consolidation covers every memory once, oldest first, and never skips one it could not see.

Mock stores ignore filters and ordering, so they cannot show a backlog drained across runs, a stamp that
jumps over memories a source did not return, consolidation's own output re-entering the window, or another
scope's memories reaching it. Each case drives a real manager over SQLite and an embedded Qdrant. A document
that cannot be decoded is skipped on its own: it must hide neither its neighbours nor the memories beyond it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    ConsolidationResponse,
    MergeOp,
    get_last_consolidated_at,
    run_consolidation,
    should_consolidate,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_INSIGHT_TAG
from myrm_agent_harness.toolkits.memory.strategies.consolidation_window import fetch_candidate_window
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, MemoryType, ProceduralMemory, SemanticMemory
from myrm_agent_harness.toolkits.vector.base import FilterDict, VectorDocument
from tests.support.consolidation_seeds import (
    GLOBAL,
    HORIZON,
    NewManager,
    at,
    episodic,
    llm_returning,
    seed,
    seed_undecodable,
    semantic,
)


def make_episodic_unreadable(manager: MemoryManager, monkeypatch: pytest.MonkeyPatch) -> None:
    vector, _ = manager._vec()
    scroll = vector.scroll

    async def flaky(
        collection: str,
        *,
        limit: int = 100,
        offset: str | None = None,
        filters: FilterDict | None = None,
        order_by: tuple[str, str] | None = None,
    ) -> tuple[list[VectorDocument], str | None]:
        if collection == manager.config.episodic_collection:
            raise RuntimeError("episodic collection unreachable")
        return await scroll(collection, limit=limit, offset=offset, filters=filters, order_by=order_by)

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


async def test_a_memory_stored_after_the_horizon_waits_for_the_next_run(new_manager: NewManager) -> None:
    manager = new_manager()
    day = 86_400
    await seed(manager, [semantic("settled", 1), semantic("ahead 1", 2 * day), semantic("ahead 2", 3 * day)])

    window = await fetch_candidate_window(manager, None, 1, HORIZON)

    # A stamp past the run's own horizon would be ignored by the time gates, so a drain would restart from
    # the oldest memory: what arrives after the horizon is left for the run that comes after it.
    assert [m.content for m in window.memories] == ["settled"]
    assert window.advance_to == HORIZON


async def test_consolidations_own_output_and_the_fragments_it_folded_never_re_enter_the_window(
    new_manager: NewManager,
) -> None:
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

    stats = await run_consolidation(manager, llm_returning(response), ConsolidationConfig())

    # The run wrote a merged memory and an insight and folded the two sources into the merge; the correction a user
    # made is all that is left to analyze.
    assert stats.merged == 1
    window = await fetch_candidate_window(manager, None, 100, datetime.now(UTC))
    assert [m.content for m in window.memories] == [correction.content]


async def test_memories_the_user_archived_or_switched_off_are_not_analyzed(new_manager: NewManager) -> None:
    manager = new_manager()
    live, other = semantic("User drinks green tea every morning", 1), semantic("User keeps a standing desk", 2)
    trashed, silenced = semantic("User likes green tea early in the day", 3), semantic("User rides a bicycle", 4)
    await seed(manager, [live, other, trashed, silenced])
    await manager.update_memory(trashed.id, status=MemoryStatus.ARCHIVED)
    await manager.update_memory(silenced.id, status=MemoryStatus.DISABLED)

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == [live.content, other.content]
    assert window.advance_to == HORIZON  # they are skipped on purpose, so the stamp moves past them


async def test_a_deleted_memory_is_neither_shown_to_the_model_nor_merged_back_into_a_live_one(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    live, other = semantic("User drinks green tea every morning", 1), semantic("User keeps a standing desk", 2)
    deleted = semantic("User secretly drinks whisky", 3)
    await seed(manager, [live, other, deleted])
    await manager.update_memory(deleted.id, status=MemoryStatus.ARCHIVED)
    merge = MergeOp(source_ids=[live.id[:8], deleted.id[:8]], merged_content="User drinks green tea and whisky")
    llm = llm_returning(ConsolidationResponse(operations=[merge]))

    stats = await run_consolidation(manager, llm, ConsolidationConfig(soft_lock_hours=0.0))

    messages = llm.with_structured_output.return_value.ainvoke.await_args.args[0]
    assert not any("whisky" in str(message.content) for message in messages)
    assert (stats.input_count, stats.merged, stats.undo.change_count) == (2, 0, 0)
    contents = [m.content for m in await manager.list_memories(MemoryType.SEMANTIC)]
    assert sorted(contents) == sorted([live.content, other.content])


async def test_an_unreadable_source_holds_the_stamp_but_still_yields_the_other_sources(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    await seed(manager, [semantic(f"fact {i}", i) for i in range(1, 4)])
    make_episodic_unreadable(manager, monkeypatch)

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == ["fact 1", "fact 2", "fact 3"]
    assert window.advance_to is None


async def test_an_undecodable_document_is_skipped_even_where_a_source_is_cut_short(new_manager: NewManager) -> None:
    manager = new_manager()
    # The semantic source is read up to its third document, which cannot be decoded; its later memories lie
    # beyond that cut, and the episodic memory is newer than the cut.
    await seed(manager, [semantic("fact 1", 1), semantic("fact 2", 2)])
    await seed_undecodable(manager, 3)
    await seed(manager, [semantic("fact 4", 4), semantic("fact 5", 5), episodic("event 6", 6)])

    first = await fetch_candidate_window(manager, None, 3, HORIZON)
    assert [m.content for m in first.memories] == ["fact 1", "fact 2"]
    assert first.advance_to == at(3)

    second = await fetch_candidate_window(manager, first.advance_to, 3, HORIZON)
    assert [m.content for m in second.memories] == ["fact 4", "fact 5", "event 6"]
    assert second.advance_to == HORIZON


async def test_a_batch_that_decodes_to_nothing_holds_the_stamp_until_a_memory_can_be_read(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    await seed_undecodable(manager, 1)
    await seed_undecodable(manager, 2)

    stuck = await fetch_candidate_window(manager, None, 100, HORIZON)
    # When nothing decodes, the converter is more likely broken than the data: the stamp must not move on.
    assert (stuck.memories, stuck.advance_to) == ([], None)

    await seed(manager, [semantic("fact 3", 3)])
    recovered = await fetch_candidate_window(manager, None, 100, HORIZON)
    assert [m.content for m in recovered.memories] == ["fact 3"]
    assert recovered.advance_to == HORIZON


async def test_a_source_that_was_never_written_is_empty_not_unreadable(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(manager, [semantic("fact", 1)])

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == ["fact"]
    assert window.advance_to == HORIZON


async def test_a_run_covers_only_the_memories_of_its_own_scope(new_manager: NewManager) -> None:
    mine, other = new_manager(), new_manager(["agent:other"])
    await mine.store(SemanticMemory(content="fact of mine"), _bypass_approval=True)
    await other.store(SemanticMemory(content="fact of the other agent"), _bypass_approval=True)

    window = await fetch_candidate_window(mine, None, 100, datetime.now(UTC) + timedelta(minutes=1))

    assert [m.content for m in window.memories] == ["fact of mine"]


async def test_rules_never_reach_the_window_and_never_hold_the_stamp(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(manager, [semantic("fact", 1)])
    await manager.store(
        ProceduralMemory(content="When: asked → Do: answer", trigger="asked", action="answer"), _bypass_approval=True
    )
    await manager._rel().create_rule(
        ProceduralMemory(content="When: later → Do: act", trigger="later", action="act", scope=GLOBAL)
    )

    window = await fetch_candidate_window(manager, None, 100, HORIZON)

    assert [m.content for m in window.memories] == ["fact"]
    assert window.advance_to == HORIZON


async def test_consecutive_runs_drain_a_backlog_and_leave_the_stamp_at_the_latest_settled_instant(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    await seed(manager, [semantic(f"fact {i}", i) for i in range(250)])
    llm, config = llm_returning(ConsolidationResponse()), ConsolidationConfig(max_memories=100)

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
    llm, config = llm_returning(ConsolidationResponse()), ConsolidationConfig()

    with monkeypatch.context() as degraded:
        make_episodic_unreadable(manager, degraded)
        stats = await run_consolidation(manager, llm, config)
    assert stats.input_count == 2
    assert await get_last_consolidated_at(manager) is None

    await run_consolidation(manager, llm, config)
    assert await get_last_consolidated_at(manager) is not None


async def test_one_undecodable_document_does_not_stall_consolidation(
    new_manager: NewManager, caplog: pytest.LogCaptureFixture
) -> None:
    manager = new_manager()
    await seed(manager, [semantic("fact 1", 1), semantic("fact 2", 2)])
    undecodable_id = await seed_undecodable(manager, 3)
    await seed(manager, [semantic("fact 4", 4), semantic("fact 5", 5)])

    with caplog.at_level(logging.WARNING):
        stats = await run_consolidation(manager, llm_returning(ConsolidationResponse()), ConsolidationConfig())

    assert stats.input_count == 4
    assert await get_last_consolidated_at(manager) is not None
    # The skip is reported by document id and failure type, never by the memory's content.
    reports = [r.getMessage() for r in caplog.records if undecodable_id in r.getMessage()]
    assert len(reports) == 1
    assert "ValidationError" in reports[0]
    assert "private note" not in reports[0]


async def test_each_owner_namespace_keeps_its_own_stamp(new_manager: NewManager) -> None:
    global_manager = new_manager(["global"])
    project_manager = new_manager(["project:p1", "global"])

    await run_consolidation(project_manager, llm_returning(ConsolidationResponse()), ConsolidationConfig())

    assert await get_last_consolidated_at(project_manager) is not None
    assert await get_last_consolidated_at(global_manager) is None
    assert await should_consolidate(global_manager, ConsolidationConfig()) is True
