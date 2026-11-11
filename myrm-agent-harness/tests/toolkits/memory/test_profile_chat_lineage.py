"""A chat's working state and the profile proposals it raised leave with the chat; the facts the user keeps do not.

The extractor writes the digest of a finished task as the working state that primes the next chats, and every profile
fact it infers first waits in the approval queue as a proposal. Both derive from one chat, so deleting the chat takes
them along whatever their status, while an ordinary profile fact (approved or typed in) stays: it is the user's now.
Real manager over an embedded Qdrant and SQLite; the entries go through the persistence step the extraction run uses.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from myrm_agent_harness.agent._internals.memory_extraction import persist_extracted_memories
from myrm_agent_harness.toolkits.memory._internal.storage import (
    WORKING_STATE_PROFILE_KEY,
    WORKING_STATE_UPDATED_AT_KEY,
    MemoryRejectedError,
)
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import close_chat
from myrm_agent_harness.toolkits.memory.strategies.extractor.models import ExtractedMemory
from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord
from tests.support.consolidation_seeds import NewManager

SCOPE = ["agent:x"]


def digest_of(title: str) -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.TASK_DIGEST,
        content=f"**Title**: {title}\n**Goal**: {title} for the team\n**Result**: done",
        confidence=0.9,
    )


def preference(key: str, value: str) -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PROFILE,
        content=f"{key}: {value}",
        confidence=0.9,
        profile_key=key,
        profile_value=value,
    )


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {kind: count for kind, count in counts.items() if count}


async def profile_proposals(manager: MemoryManager) -> list[PendingRecord]:
    return [record for record in await manager.list_pending() if record.memory_type == MemoryType.PROFILE]


async def working_state(manager: MemoryManager) -> str | None:
    state = (await manager.get_context()).get("working_state")
    return state if isinstance(state, str) else None


async def approve_all(manager: MemoryManager) -> None:
    for record in await profile_proposals(manager):
        await manager.approve(record.id)


# ── Working state ────────────────────────────────────────────────────


async def test_a_working_state_written_from_a_chat_goes_with_the_chat(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE)
    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a", force_pending=False)
    cascade = new_manager(all_scopes=True)

    assert "Quarterly report" in str(await working_state(manager))
    assert (await cascade.count_by_source_chat_id("chat-a"))["profile"] == 2
    assert (await cascade.purge_by_source_chat_id("chat-a"))["profile"] == 2
    assert await working_state(manager) is None


async def test_a_working_state_proposal_waits_linked_to_its_chat_and_goes_with_it(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a")
    cascade = new_manager(all_scopes=True)

    proposals = await profile_proposals(manager)
    assert {record.memory_data["key"] for record in proposals} == {
        WORKING_STATE_PROFILE_KEY,
        WORKING_STATE_UPDATED_AT_KEY,
    }
    assert {record.source_chat_id for record in proposals} == {"chat-a"}
    assert await working_state(manager) is None

    await cascade.purge_by_source_chat_id("chat-a")
    assert await profile_proposals(manager) == []


async def test_an_approved_working_state_goes_with_the_chat_and_so_does_its_approval_record(
    new_manager: NewManager,
) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a")
    await approve_all(manager)
    cascade = new_manager(all_scopes=True)

    assert "Quarterly report" in str(await working_state(manager))
    counts = await cascade.count_by_source_chat_id("chat-a")
    assert counts["profile"] == 2
    assert counts["pending"] >= 2  # both resolved proposals keep the digest text

    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == counts
    assert await working_state(manager) is None
    assert [record for record in await manager.list_pending() if record.source_chat_id == "chat-a"] == []


async def test_a_rejected_working_state_proposal_goes_with_the_chat(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a")
    for record in await profile_proposals(manager):
        await manager.reject(record.id)
    cascade = new_manager(all_scopes=True)

    assert (await cascade.count_by_source_chat_id("chat-a"))["pending"] >= 2
    await cascade.purge_by_source_chat_id("chat-a")
    assert await cascade.count_by_source_chat_id("chat-a") == {}


async def test_the_chat_that_wrote_the_state_last_owns_it(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE)
    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a", force_pending=False)
    await persist_extracted_memories([digest_of("Travel plan")], manager, "chat-b", force_pending=False)

    await manager.purge_by_source_chat_id("chat-a")
    assert "Travel plan" in str(await working_state(manager))

    await manager.purge_by_source_chat_id("chat-b")
    assert await working_state(manager) is None


async def test_a_state_the_user_wrote_stays_when_the_chat_it_replaced_is_deleted(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE)
    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a", force_pending=False)
    await manager.set_system_profile_attribute(WORKING_STATE_PROFILE_KEY, "my own note")
    await manager.set_system_profile_attribute(WORKING_STATE_UPDATED_AT_KEY, datetime.now(UTC).isoformat())

    assert "profile" not in await manager.count_by_source_chat_id("chat-a")
    assert "profile" not in await manager.purge_by_source_chat_id("chat-a")
    assert await working_state(manager) == "my own note"


async def test_every_agent_working_state_of_the_chat_goes_with_it(new_manager: NewManager) -> None:
    first, second = new_manager(["agent:x"]), new_manager(["agent:y"])
    await persist_extracted_memories([digest_of("Quarterly report")], first, "chat-a", force_pending=False)
    await persist_extracted_memories([digest_of("Quarterly report")], second, "chat-a", force_pending=False)

    assert (await new_manager(all_scopes=True).purge_by_source_chat_id("chat-a"))["profile"] == 4
    assert await working_state(first) is None
    assert await working_state(second) is None


# ── Ordinary profile facts ───────────────────────────────────────────


async def test_an_approved_profile_fact_outlives_the_chat_that_proposed_it(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await persist_extracted_memories([preference("reply_style", "brief answers")], manager, "chat-a")
    [proposal] = await profile_proposals(manager)
    assert proposal.source_chat_id == "chat-a"
    await manager.approve(proposal.id)
    cascade = new_manager(all_scopes=True)

    counts = await cascade.count_by_source_chat_id("chat-a")
    assert counts == {"pending": 1}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == counts
    assert await manager.get_profile_attribute("reply_style") == "brief answers"
    assert await manager.list_pending() == []


async def test_an_unapproved_profile_proposal_goes_with_the_chat(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await persist_extracted_memories([preference("reply_style", "brief answers")], manager, "chat-a")
    await persist_extracted_memories([preference("timezone", "UTC+8")], manager, "chat-b")

    await manager.purge_by_source_chat_id("chat-a")

    assert [record.memory_data["key"] for record in await profile_proposals(manager)] == ["timezone"]


async def test_a_directly_written_profile_fact_is_not_linked_to_the_chat_that_saved_it(
    new_manager: NewManager,
) -> None:
    manager = new_manager(SCOPE)
    assert await manager.set_profile_attribute("reply_style", "brief answers", source_chat_id="chat-a") is None
    assert await manager.set_profile_attribute("__working_state", "digest", source_chat_id="chat-a") is None

    assert nonzero(await manager.purge_by_source_chat_id("chat-a")) == {"profile": 1}
    assert await manager.get_profile_attribute("reply_style") == "brief answers"
    assert await manager.get_profile_attribute("__working_state") is None


async def test_a_fact_the_user_typed_is_never_linked(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE)
    await manager.set_profile_attribute("reply_style", "brief answers")
    await manager.set_system_profile_attribute("__working_state", "my own note")

    assert nonzero(await manager.purge_by_source_chat_id("chat-a")) == {}
    assert await manager.get_profile_attribute("reply_style") == "brief answers"
    assert await manager.get_profile_attribute("__working_state") == "my own note"


# ── Deleted-chat fence ───────────────────────────────────────────────


async def test_a_profile_proposal_from_a_deleted_chat_is_refused(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await manager.purge_by_source_chat_id("chat-a")

    await persist_extracted_memories([preference("reply_style", "brief answers")], manager, "chat-a")
    assert await profile_proposals(manager) == []

    queued = await manager.set_profile_attribute("reply_style", "brief", _force_pending=True, source_chat_id="chat-a")
    assert queued == ""
    assert await profile_proposals(manager) == []


async def test_a_working_state_from_a_deleted_chat_is_not_written(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE)
    await manager.purge_by_source_chat_id("chat-a")

    await persist_extracted_memories([digest_of("Quarterly report")], manager, "chat-a", force_pending=False)

    assert await working_state(manager) is None
    assert await manager.count_by_source_chat_id("chat-a") == {}


async def test_a_proposal_cannot_be_approved_once_its_chat_was_deleted(new_manager: NewManager) -> None:
    manager = new_manager(SCOPE, approval_required=True)
    await persist_extracted_memories([preference("reply_style", "brief answers")], manager, "chat-a")
    [proposal] = await profile_proposals(manager)
    close_chat("u1", "chat-a")  # the purge has begun but has not reached the queue yet

    with pytest.raises(MemoryRejectedError):
        await manager.approve(proposal.id)

    assert await manager.get_profile_attribute("reply_style") is None


# ── Schema ───────────────────────────────────────────────────────────

_PROFILES_WITH_NAMESPACES = """CREATE TABLE profiles (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
    primary_namespace TEXT NOT NULL DEFAULT '', namespaces TEXT NOT NULL DEFAULT '[]',
    agent_id TEXT, channel_id TEXT, conversation_id TEXT, task_id TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""

_PROFILES_BEFORE_NAMESPACES = """CREATE TABLE profiles (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""


@pytest.mark.parametrize("old_table", [_PROFILES_WITH_NAMESPACES, _PROFILES_BEFORE_NAMESPACES])
async def test_a_database_created_before_the_profile_chat_link_gains_it_and_keeps_its_facts(
    tmp_path: Path, old_table: str
) -> None:
    db_path = tmp_path / "old_profiles.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(old_table)
        conn.execute(
            "INSERT INTO profiles (id, user_id, key, value, created_at, updated_at) "
            "VALUES ('old', 'default', 'timezone', 'UTC+8', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')"
        )

    store = SQLiteRelationalStore(str(db_path))
    try:
        await store.set_profile("__working_state", "digest", source_chat_id="chat-a")

        assert await store.count_profiles_by_source_chat_id("chat-a") == 1
        assert await store.delete_profiles_by_source_chat_id("chat-a") == 1
        assert await store.get_profile("timezone") == "UTC+8"
    finally:
        await store.close()
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(profiles)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(profiles)")}
    assert "source_chat_id" in columns
    assert "idx_profiles_source_chat" in indexes
