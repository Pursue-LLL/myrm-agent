"""Tests for the consolidation cursor: the stamp, its time gate and the candidate window.

Covers:
- get_last_consolidated_at / should_consolidate time gates
- fetch_candidate_window: vector scroll (consolidation-event skip), relational rules, truncation,
  per-store error tolerance and the stamp each outcome allows
- _advance_stamp persistence guards
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    _advance_stamp,
    get_last_consolidated_at,
    should_consolidate,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import _PROFILE_KEY_LAST_CONSOLIDATED
from myrm_agent_harness.toolkits.memory.strategies.consolidation_window import fetch_candidate_window
from myrm_agent_harness.toolkits.memory.types import ProceduralMemory
from myrm_agent_harness.toolkits.vector.base import VectorDocument
from tests.support.consolidation_manager import make_manager, semantic_doc


def _episodic_doc(mem_id: str, content: str, *, event_type: str = "conversation") -> VectorDocument:
    return VectorDocument(
        id=mem_id,
        content=content,
        metadata={"user_id": "test-user", "event_type": event_type},
        created_at=datetime.now(UTC) - timedelta(days=1),
    )


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
    async def test_invalid_raw_value_returns_none(self) -> None:
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value="not-a-date")
        assert await get_last_consolidated_at(manager) is None

    @pytest.mark.asyncio
    async def test_valid_raw_value_parsed(self) -> None:
        manager = make_manager()
        ts = datetime.now(UTC)
        manager._rel_store.get_profile = AsyncMock(return_value=ts.isoformat())
        parsed = await get_last_consolidated_at(manager)
        assert parsed is not None
        assert abs((parsed - ts).total_seconds()) < 1


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
    async def test_vector_and_relational_combined_truncated(self) -> None:
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
        manager._rel_store.list_rules = AsyncMock(
            return_value=[
                ProceduralMemory(
                    content="rule",
                    trigger="t",
                    action="a",
                    created_at=datetime.now(UTC) - timedelta(hours=1),
                )
            ]
        )
        window = await fetch_candidate_window(
            manager, since=datetime.now(UTC) - timedelta(days=3), max_count=2, horizon=datetime.now(UTC)
        )
        assert len(window.memories) == 2
        assert all(hasattr(m, "created_at") for m in window.memories)
        # More candidates than one window holds: only what the window reached is covered.
        assert window.advance_to == window.memories[-1].created_at

    @pytest.mark.asyncio
    async def test_consolidation_event_skipped(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        vector.scroll = AsyncMock(
            side_effect=[
                ([], None),
                ([_episodic_doc("consol", "event", event_type="consolidation")], None),
            ]
        )
        horizon = datetime.now(UTC)
        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=horizon)
        assert window.memories == []
        assert window.advance_to == horizon

    @pytest.mark.asyncio
    async def test_vector_scroll_error_is_tolerated(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        vector.scroll = AsyncMock(side_effect=RuntimeError("vector down"))
        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=datetime.now(UTC))
        assert window.memories == []
        assert window.advance_to is None

    @pytest.mark.asyncio
    async def test_no_vector_uses_relational_only(self) -> None:
        manager = make_manager()
        manager.has_vector = False
        manager._rel_store.list_rules = AsyncMock(
            return_value=[ProceduralMemory(content="rule", trigger="t", action="a")]
        )
        horizon = datetime.now(UTC)
        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=horizon)
        assert len(window.memories) == 1
        assert window.advance_to == horizon

    @pytest.mark.asyncio
    async def test_relational_error_is_tolerated(self) -> None:
        manager = make_manager()
        vector = manager._vec_store
        vector.scroll = AsyncMock(side_effect=[([semantic_doc("s-1", "fact")], None), ([], None)])
        manager._rel_store.list_rules = AsyncMock(side_effect=RuntimeError("rel down"))
        window = await fetch_candidate_window(manager, since=None, max_count=5, horizon=datetime.now(UTC))
        assert len(window.memories) == 1
        assert window.advance_to is None


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
