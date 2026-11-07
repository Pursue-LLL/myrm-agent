"""Maintenance counters and timestamps tolerate bookkeeping rows that other callers wrote.

A ``_system.`` profile key is an ordinary row to the public write path, so a caller can store a
value the maintenance code would never write itself. Each case plants such a value in a real
SQLite-backed manager and checks that consolidation and pattern discovery keep working instead of
raising or stalling.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig, MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies import consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    ConsolidationStats,
    get_last_consolidated_at,
    run_consolidation,
    should_consolidate,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import _PROFILE_KEY_LAST_CONSOLIDATED
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    _PROFILE_KEY_CONSOLIDATION_COUNT,
    increment_consolidation_count,
    should_run_pattern_discovery,
)

_UNUSABLE_TIMESTAMPS = {
    "naive": datetime(2026, 1, 1).isoformat(),
    "future": (datetime.now(UTC) + timedelta(days=36500)).isoformat(),
}


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[MemoryManager]:
    store = SQLiteRelationalStore(str(tmp_path / "bookkeeping.db"))
    yield MemoryManager(MemoryConfig(embedding_model="test"), user_id="u1", relational=store, auto_warmup=False)
    await store.close()


@pytest.fixture
def mature_manager(manager: MemoryManager, monkeypatch: pytest.MonkeyPatch) -> MemoryManager:
    """A manager that already satisfies the memory-count conditions of the pattern-discovery gate."""
    monkeypatch.setattr(MemoryManager, "has_vector", property(lambda _self: True))
    monkeypatch.setattr(manager, "count_memories", AsyncMock(return_value=30))
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["abc", "-5"])
async def test_increment_replaces_an_unusable_counter(manager: MemoryManager, raw: str) -> None:
    await manager.set_profile_attribute(_PROFILE_KEY_CONSOLIDATION_COUNT, raw)

    await increment_consolidation_count(manager)

    assert await manager.get_profile_attribute(_PROFILE_KEY_CONSOLIDATION_COUNT) == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "opens"), [("3", True), ("abc", False)])
async def test_discovery_gate_reads_the_counter_defensively(
    mature_manager: MemoryManager, raw: str, opens: bool
) -> None:
    await mature_manager.set_profile_attribute(_PROFILE_KEY_CONSOLIDATION_COUNT, raw)

    assert await should_run_pattern_discovery(mature_manager) is opens


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", _UNUSABLE_TIMESTAMPS.values(), ids=list(_UNUSABLE_TIMESTAMPS))
async def test_unusable_timestamp_reads_as_never_consolidated(manager: MemoryManager, raw: str) -> None:
    await manager.set_profile_attribute(_PROFILE_KEY_LAST_CONSOLIDATED, raw)

    assert await get_last_consolidated_at(manager) is None
    assert await should_consolidate(manager, ConsolidationConfig()) is True


@pytest.mark.asyncio
async def test_recent_timestamp_still_holds_consolidation_back(manager: MemoryManager) -> None:
    last = datetime.now(UTC) - timedelta(hours=1)
    await manager.set_profile_attribute(_PROFILE_KEY_LAST_CONSOLIDATED, last.isoformat())

    assert await get_last_consolidated_at(manager) == last
    assert await should_consolidate(manager, ConsolidationConfig(interval_hours=24)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", _UNUSABLE_TIMESTAMPS.values(), ids=list(_UNUSABLE_TIMESTAMPS))
async def test_run_consolidation_gets_past_the_soft_lock_with_an_unusable_timestamp(
    manager: MemoryManager, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(consolidation, "_fetch_incremental_memories", fetch)
    await manager.set_profile_attribute(_PROFILE_KEY_LAST_CONSOLIDATED, raw)

    assert await run_consolidation(manager, AsyncMock(), ConsolidationConfig()) == ConsolidationStats()
    fetch.assert_awaited_once()
