"""Internal bookkeeping profile rows never surface in a listing or a count.

The maintenance strategies persist their counters and timestamps as profile rows. The store hides
them by key prefix, so the prefix it filters on must be the one those writers really use: the keys
below are the writers' own constants, not copies of their text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import _PROFILE_KEY_LAST_CONSOLIDATED
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    _PROFILE_KEY_CONSOLIDATION_COUNT,
    _PROFILE_KEY_LAST_PATTERN_DISCOVERY,
    _PROFILE_KEY_MEMORY_SET_HASH,
)

BOOKKEEPING_KEYS = (
    _PROFILE_KEY_CONSOLIDATION_COUNT,
    _PROFILE_KEY_LAST_CONSOLIDATED,
    _PROFILE_KEY_LAST_PATTERN_DISCOVERY,
    _PROFILE_KEY_MEMORY_SET_HASH,
)


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteRelationalStore:
    s = SQLiteRelationalStore(str(tmp_path / "internal_keys.db"))
    yield s  # type: ignore[misc]
    await s.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("key", BOOKKEEPING_KEYS)
async def test_bookkeeping_key_is_hidden_from_list_and_count(store: SQLiteRelationalStore, key: str) -> None:
    await store.set_profile(key, "1")
    await store.set_profile("language", "zh")

    assert [entry.key for entry in await store.list_profiles()] == ["language"]
    assert await store.count_profiles() == 1
    assert await store.get_profile(key) == "1"


@pytest.mark.asyncio
async def test_only_the_dotted_prefix_is_internal(store: SQLiteRelationalStore) -> None:
    await store.set_profile("_system_note", "kept")

    assert [entry.key for entry in await store.list_profiles()] == ["_system_note"]
    assert await store.count_profiles() == 1
