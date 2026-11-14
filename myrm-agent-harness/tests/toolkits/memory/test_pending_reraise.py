"""A repeated proposal raises the one that waits: it moves to the front of the queue and takes the repeat's time.

An agent that proposes a preference, then its opposite, then the first again leaves two open proposals, not three:
the repeat is not queued twice. Approved together, they must rank in the order the user last asked, so the preference
the user changed back to leads. The queue cases drive the SQLite store; the ranking case drives a real manager and
reads the rules where the prompt reads them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord
from tests.support.memory_save_surfaces import SAVES, Save
from tests.support.relational_records import make_pending

NewManager = Callable[..., MemoryManager]

EARLIER = "2026-01-01T00:00:00+00:00"
LATER = "2026-02-01T00:00:00+00:00"
LATEST = "2026-03-01T00:00:00+00:00"
TRIGGER = "when summarizing code changes"
PLAIN = "Reply in one plain sentence"
BULLETED = "Reply with a bulleted list"
TICK = 0.002  # the queue orders by a microsecond clock; a tick keeps two submissions apart


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    s = SQLiteRelationalStore(str(tmp_path / "test_rel.db"))
    yield s
    await s.close()


def dated(content: str, created_at: str, **payload: str) -> PendingRecord:
    return PendingRecord(
        memory_type=MemoryType.SEMANTIC, content=content, memory_data={"created_at": created_at, **payload}
    )


def timezone_entry() -> PendingRecord:
    return PendingRecord(
        memory_type=MemoryType.PROFILE, content="timezone=UTC", memory_data={"key": "timezone", "value": "UTC"}
    )


async def test_a_repeated_proposal_moves_the_waiting_one_to_the_front(store: SQLiteRelationalStore) -> None:
    first = await store.submit_pending(make_pending("A"))
    await asyncio.sleep(TICK)
    second = await store.submit_pending(make_pending("B"))
    assert [record.id for record in await store.list_pending()] == [second, first]
    await asyncio.sleep(TICK)

    repeated = await store.submit_pending(make_pending("A"))

    assert repeated == ""
    assert [record.id for record in await store.list_pending()] == [first, second]


async def test_the_waiting_proposal_takes_the_creation_time_of_the_repeat_and_keeps_the_rest(
    store: SQLiteRelationalStore,
) -> None:
    first = await store.submit_pending(dated("A", EARLIER, note="first"))

    repeated = await store.submit_pending(dated("A", LATER, note="second"))

    waiting = await store.get_pending(first)
    assert repeated == ""
    assert waiting is not None
    assert waiting.memory_data == {"created_at": LATER, "note": "first"}


async def test_a_proposal_without_a_creation_time_only_moves_to_the_front(store: SQLiteRelationalStore) -> None:
    first = await store.submit_pending(timezone_entry())
    await asyncio.sleep(TICK)
    second = await store.submit_pending(make_pending("B"))
    await asyncio.sleep(TICK)

    repeated = await store.submit_pending(timezone_entry())

    waiting = await store.get_pending(first)
    assert repeated == ""
    assert [record.id for record in await store.list_pending()] == [first, second]
    assert waiting is not None
    assert waiting.memory_data == {"key": "timezone", "value": "UTC"}


@pytest.mark.parametrize("resolution", ["approved", "rejected"])
async def test_only_the_open_proposal_is_raised_when_a_resolved_one_has_the_same_text(
    store: SQLiteRelationalStore, resolution: str
) -> None:
    resolved_id = await store.submit_pending(dated("A", EARLIER))
    await store.mark_pending(resolved_id, resolution)
    open_id = await store.submit_pending(dated("A", LATER))

    repeated = await store.submit_pending(dated("A", LATEST))

    resolved = await store.get_pending(resolved_id)
    waiting = await store.get_pending(open_id)
    assert open_id not in ("", resolved_id)
    assert repeated == ""
    assert resolved is not None
    assert (resolved.status, resolved.memory_data["created_at"]) == (resolution, EARLIER)
    assert waiting is not None
    assert (waiting.status, waiting.memory_data["created_at"]) == ("pending", LATEST)


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize("oldest_first", [False, True], ids=["newest-first", "oldest-first"])
async def test_a_preference_changed_and_changed_back_leads_when_approved_together(
    new_manager: NewManager, save: Save, oldest_first: bool
) -> None:
    manager = new_manager(approval_required=True)
    replies = []
    for action in (PLAIN, BULLETED, PLAIN):
        replies.append(await save(manager, {"category": "rule", "rule_trigger": TRIGGER, "content": action}))
        await asyncio.sleep(TICK)
    pending = await manager.list_pending()

    assert "already waiting for the user's approval" in replies[2]
    assert len(pending) == 2
    for record in reversed(pending) if oldest_first else pending:
        assert await manager.approve(record.id) is not None
        await asyncio.sleep(TICK)

    rules = (await manager.get_context())["rules"]
    assert isinstance(rules, list)
    assert [rule["action"] for rule in rules] == [PLAIN, BULLETED]
