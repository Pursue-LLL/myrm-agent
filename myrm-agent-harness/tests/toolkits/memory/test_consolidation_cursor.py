"""Tests for the consolidation cursor: the stamp, its time gate and the candidate window.

Covers:
- get_last_consolidated_at / should_consolidate time gates
- fetch_candidate_window: the arrival-ordered read of each source and the stamp that precedes it,
  truncation (never through one instant), per-store error tolerance and the stamp each outcome allows
- _advance_stamp persistence guards
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory._internal.store_stamp import STORED_TS_KEY
from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    _advance_stamp,
    get_last_consolidated_at,
    should_consolidate,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import _PROFILE_KEY_LAST_CONSOLIDATED
from myrm_agent_harness.toolkits.memory.strategies.consolidation_window import fetch_candidate_window
from myrm_agent_harness.toolkits.vector.base import FilterDict, VectorDocument
from tests.support.consolidation_manager import make_manager, semantic_doc


def _episodic_doc(mem_id: str, content: str) -> VectorDocument:
    created_at = datetime.now(UTC) - timedelta(days=1)
    return VectorDocument(
        id=mem_id,
        content=content,
        metadata={"user_id": "test-user", "event_type": "conversation", STORED_TS_KEY: created_at.timestamp()},
        created_at=created_at,
    )


def _doc_at(mem_id: str, arrived: datetime, *, event_type: str | None = None) -> VectorDocument:
    """A semantic document, or an episodic one when ``event_type`` is given, that reached the store at ``arrived``."""
    metadata: dict[str, str | int | float | bool] = {"user_id": "test-user", STORED_TS_KEY: arrived.timestamp()}
    if event_type is None:
        metadata |= {"importance": 0.8, "confidence": 0.9}
    else:
        metadata["event_type"] = event_type
    return VectorDocument(id=mem_id, content=mem_id, metadata=metadata, created_at=arrived)


class TestLastConsolidatedAt:
    @pytest.mark.asyncio
    async def test_no_relational_returns_none(self) -> None:
        manager = make_manager()
        manager.has_relational = False
        assert await get_last_consolidated_at(manager) is None

    @pytest.mark.asyncio
    async def test_no_raw_value_returns_none(self) -> None:
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value=None)
        assert await get_last_consolidated_at(manager) is None

    @pytest.mark.asyncio
    async def test_invalid_raw_value_is_ignored_with_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value="not-a-date")
        with caplog.at_level(logging.WARNING):
            assert await get_last_consolidated_at(manager) is None
        assert "'not-a-date' cannot be parsed; ignored" in caplog.text

    @pytest.mark.asyncio
    async def test_naive_raw_value_is_ignored_with_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        manager = make_manager()
        raw = datetime.now().replace(tzinfo=None).isoformat()
        manager._rel_store.get_profile = AsyncMock(return_value=raw)
        with caplog.at_level(logging.WARNING):
            assert await get_last_consolidated_at(manager) is None
        assert f"stamp {raw} is naive or ahead of the wall clock; ignored" in caplog.text

    @pytest.mark.asyncio
    async def test_raw_value_ahead_of_the_wall_clock_is_ignored_with_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager = make_manager()
        raw = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        manager._rel_store.get_profile = AsyncMock(return_value=raw)
        with caplog.at_level(logging.WARNING):
            assert await get_last_consolidated_at(manager) is None
        assert f"stamp {raw} is naive or ahead of the wall clock; ignored" in caplog.text

    @pytest.mark.asyncio
    async def test_valid_raw_value_parsed_without_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        manager = make_manager()
        ts = datetime.now(UTC) - timedelta(minutes=1)
        manager._rel_store.get_profile = AsyncMock(return_value=ts.isoformat())
        with caplog.at_level(logging.WARNING):
            parsed = await get_last_consolidated_at(manager)
        assert parsed == ts
        assert caplog.records == []


class TestShouldConsolidate:
    @pytest.mark.asyncio
    async def test_disabled_returns_false(self) -> None:
        config = ConsolidationConfig(enabled=False)
        assert await should_consolidate(make_manager(), config) is False

    @pytest.mark.asyncio
    async def test_no_last_consolidation_returns_true(self) -> None:
        config = ConsolidationConfig()
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value=None)
        assert await should_consolidate(manager, config) is True

    @pytest.mark.asyncio
    async def test_elapsed_below_interval_returns_false(self) -> None:
        config = ConsolidationConfig(interval_hours=24)
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value=datetime.now(UTC).isoformat())
        assert await should_consolidate(manager, config) is False

    @pytest.mark.asyncio
    async def test_elapsed_above_interval_returns_true(self) -> None:
        config = ConsolidationConfig(interval_hours=24)
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value=(datetime.now(UTC) - timedelta(hours=25)).isoformat())
        assert await should_consolidate(manager, config) is True


class TestFetchCandidateWindow:
    @pytest.mark.asyncio
    async def test_sources_combined_and_truncated(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        vector.scroll = AsyncMock(
            side_effect=[
                (
                    [
                        semantic_doc("s-1", "semantic fact"),
                        semantic_doc("s-2", "semantic fact 2"),
                    ],
                    None,
                ),
                ([_episodic_doc("e-1", "event fact")], None),
            ]
        )
        window = await fetch_candidate_window(
            manager, since=datetime.now(UTC) - timedelta(days=3), max_count=2, horizon=datetime.now(UTC)
        )
        assert len(window.memories) == 2
        assert all(hasattr(m, "created_at") for m in window.memories)
        # More candidates than one window holds: only what the window reached is covered.
        assert window.advance_to == window.memories[-1].stored_at

    @pytest.mark.asyncio
    async def test_vector_scroll_error_is_tolerated(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        vector.scroll = AsyncMock(side_effect=RuntimeError("vector down"))
        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=datetime.now(UTC))
        assert window.memories == []
        assert window.advance_to is None

    @pytest.mark.asyncio
    async def test_no_vector_has_nothing_to_read(self) -> None:
        manager = make_manager()
        manager.has_vector = False
        horizon = datetime.now(UTC)
        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=horizon)
        assert (window.memories, window.advance_to) == ([], horizon)

    @pytest.mark.asyncio
    async def test_each_source_is_read_in_arrival_order_between_the_stamp_and_the_horizon(self) -> None:
        manager = make_manager()
        since, horizon = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)

        await fetch_candidate_window(manager, since=since, max_count=5, horizon=horizon)
        await fetch_candidate_window(manager, since=None, max_count=5, horizon=horizon)

        reads = manager._vec_store.scroll.await_args_list
        assert [call.args[0] for call in reads] == ["test_semantic", "test_episodic"] * 2
        assert {(call.kwargs["order_by"], call.kwargs["limit"]) for call in reads} == {((STORED_TS_KEY, "asc"), 6)}
        arrivals = [call.kwargs["filters"][STORED_TS_KEY] for call in reads]
        assert (
            arrivals == [{"gt": since.timestamp(), "lte": horizon.timestamp()}] * 2 + [{"lte": horizon.timestamp()}] * 2
        )

    @pytest.mark.asyncio
    async def test_documents_stored_before_stamps_existed_are_stamped_before_each_read(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        events: list[str] = []

        async def stamp(collection: str, field: str, from_field: str) -> int:
            events.append(f"stamp {collection} {field}<-{from_field}")
            return 0

        async def read(collection: str, **_: object) -> tuple[list[VectorDocument], None]:
            events.append(f"read {collection}")
            return [], None

        vector.backfill_payload_copy = AsyncMock(side_effect=stamp)
        vector.scroll = AsyncMock(side_effect=read)

        await fetch_candidate_window(manager, since=None, max_count=5, horizon=datetime.now(UTC))

        assert events == [
            "stamp test_semantic stored_ts<-_created_ts",
            "read test_semantic",
            "stamp test_episodic stored_ts<-_created_ts",
            "read test_episodic",
        ]

    @pytest.mark.asyncio
    async def test_a_source_that_cannot_be_stamped_holds_the_stamp_and_is_not_read(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        vector.backfill_payload_copy = AsyncMock(side_effect=RuntimeError("payload write failed"))

        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=datetime.now(UTC))

        assert (window.memories, window.advance_to) == ([], None)
        vector.scroll.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_cut_without_a_readable_stamp_holds_the_stamp(self) -> None:
        manager = make_manager()
        unstamped = [
            VectorDocument(id=f"s-{i}", content="fact", metadata={"user_id": "test-user"}, created_at=datetime.now(UTC))
            for i in range(3)
        ]
        manager._vec_store.scroll = AsyncMock(side_effect=[(unstamped, None), ([], None)])

        window = await fetch_candidate_window(manager, since=None, max_count=2, horizon=datetime.now(UTC))

        # Where the source was cut is unknown, so nothing it showed may count as covered.
        assert (window.memories, window.advance_to) == ([], None)

    @pytest.mark.asyncio
    async def test_memories_that_arrived_at_one_instant_are_never_split_by_the_window(self) -> None:
        manager = make_manager()
        earlier, tied, horizon = (datetime(2026, 1, day, tzinfo=UTC) for day in (1, 2, 3))
        stored = {
            "test_semantic": [_doc_at("earlier", earlier), _doc_at("tied 0", tied), _doc_at("tied 1", tied)],
            "test_episodic": [
                _doc_at("tied 2", tied, event_type="conversation"),
                _doc_at("tied 3", tied, event_type="conversation"),
            ],
        }

        async def scroll(
            collection: str, *, limit: int, filters: FilterDict, **_: object
        ) -> tuple[list[VectorDocument], None]:
            arrival = filters[STORED_TS_KEY]
            assert isinstance(arrival, dict)
            after, until = arrival.get("gt", float("-inf")), arrival["lte"]
            return [d for d in stored[collection] if after < d.metadata[STORED_TS_KEY] <= until][:limit], None

        manager._vec_store.scroll = AsyncMock(side_effect=scroll)

        first = await fetch_candidate_window(manager, None, 3, horizon)
        second = await fetch_candidate_window(manager, first.advance_to, 3, horizon)
        third = await fetch_candidate_window(manager, second.advance_to, 3, horizon)

        # A cut through the tied instant would lose the memories beyond it, because the stamp is an instant.
        assert ([m.content for m in first.memories], first.advance_to) == (["earlier"], earlier)
        assert (sorted(m.content for m in second.memories), second.advance_to) == (
            [f"tied {i}" for i in range(4)],
            tied,
        )
        assert (third.memories, third.advance_to) == ([], horizon)


class TestAdvanceStamp:
    @pytest.mark.asyncio
    async def test_no_relational_skips(self) -> None:
        manager = make_manager()
        manager.has_relational = False
        await _advance_stamp(manager, datetime.now(UTC))
        manager._rel_store.set_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_persists_isoformat_in_the_owner_namespace(self) -> None:
        manager = make_manager()
        ts = datetime.now(UTC)
        await _advance_stamp(manager, ts)
        manager._rel_store.set_profile.assert_awaited_once()
        call = manager._rel_store.set_profile.call_args
        assert call.args[0] == _PROFILE_KEY_LAST_CONSOLIDATED
        assert datetime.fromisoformat(call.args[1]) == ts
        assert call.kwargs["scope"].primary_namespace == "test-ns"

    @pytest.mark.asyncio
    async def test_unreadable_source_holds_the_stamp(self) -> None:
        manager = make_manager()
        await _advance_stamp(manager, None)
        manager._rel_store.set_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_error_is_tolerated(self) -> None:
        manager = make_manager()
        manager._rel_store.set_profile = AsyncMock(side_effect=RuntimeError("write failed"))
        await _advance_stamp(manager, datetime.now(UTC))  # must not raise
