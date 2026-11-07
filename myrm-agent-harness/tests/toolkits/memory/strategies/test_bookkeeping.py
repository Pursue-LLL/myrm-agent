"""Maintenance bookkeeping rows are system state: private to a namespace, outside governance.

Each case drives real managers over one real SQLite store, so a row that lands in the wrong
namespace, queues an approval or leaks into the chat context shows up as it would in production.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from myrm_agent_harness.core.context_vars import chat_id_var
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryConfig, MemoryWritePolicy
from myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store import get_shared_ephemeral_delta_store
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.bookkeeping import read_bookkeeping, write_bookkeeping
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    _PROFILE_KEY_CONSOLIDATION_COUNT,
    increment_consolidation_count,
)

_KEY = "_system.test_marker"


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    relational = SQLiteRelationalStore(str(tmp_path / "bookkeeping.db"))
    yield relational
    await relational.close()


def _manager(
    store: SQLiteRelationalStore,
    *,
    namespaces: list[str] | None = None,
    approval_required: bool = False,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    memory_policy: AgentMemoryPolicy | None = None,
) -> MemoryManager:
    return MemoryManager(
        MemoryConfig(embedding_model="test"),
        user_id="u1",
        relational=store,
        approval_required=approval_required,
        namespaces=namespaces,
        agent_id=agent_id,
        conversation_id=conversation_id,
        memory_policy=memory_policy,
        auto_warmup=False,
    )


@pytest.mark.asyncio
async def test_a_written_value_reads_back_and_a_missing_key_reads_as_none(store: SQLiteRelationalStore) -> None:
    manager = _manager(store, namespaces=["global"])

    assert await read_bookkeeping(manager, _KEY) is None

    await write_bookkeeping(manager, _KEY, "1")
    await write_bookkeeping(manager, _KEY, "2")

    assert await read_bookkeeping(manager, _KEY) == "2"


@pytest.mark.asyncio
async def test_managers_with_different_owner_namespaces_never_see_each_others_rows(
    store: SQLiteRelationalStore,
) -> None:
    global_manager = _manager(store, namespaces=["global"])
    agent_manager = _manager(store, namespaces=["global", "agent:alpha"])
    project_manager = _manager(store, namespaces=["project:p1", "global"])

    await write_bookkeeping(project_manager, _KEY, "project")
    await write_bookkeeping(global_manager, _KEY, "global")

    assert await read_bookkeeping(global_manager, _KEY) == "global"
    assert await read_bookkeeping(project_manager, _KEY) == "project"
    # ``global`` is in the agent manager's chain, but the row is not the agent scope's own.
    assert await read_bookkeeping(agent_manager, _KEY) is None


@pytest.mark.asyncio
async def test_a_conversation_scoped_write_policy_keeps_rows_at_the_agent_scope(
    store: SQLiteRelationalStore,
) -> None:
    policy = AgentMemoryPolicy(write_policy=MemoryWritePolicy.CONVERSATION)
    first_chat = _manager(store, agent_id="alpha", conversation_id="c1", memory_policy=policy)
    second_chat = _manager(store, agent_id="alpha", conversation_id="c2", memory_policy=policy)
    assert first_chat.scope.primary_namespace == "conversation:c1"

    await write_bookkeeping(first_chat, _KEY, "stamp")

    assert await read_bookkeeping(second_chat, _KEY) == "stamp"
    assert await store.get_profile(_KEY, namespaces=["agent:alpha"]) == "stamp"
    assert await store.get_profile(_KEY, namespaces=["conversation:c1"]) is None


@pytest.mark.asyncio
async def test_the_counter_advances_in_confirm_mode_without_queueing_an_approval(
    store: SQLiteRelationalStore,
) -> None:
    manager = _manager(store, namespaces=["global"], approval_required=True)

    for _ in range(3):
        await increment_consolidation_count(manager)

    assert await read_bookkeeping(manager, _PROFILE_KEY_CONSOLIDATION_COUNT) == "3"
    assert await store.count_pending() == 0
    # Control: the public profile path of the same manager does queue a user approval.
    assert await manager.set_profile_attribute("favorite_color", "teal") is not None
    assert await store.count_pending() == 1


@pytest.mark.asyncio
async def test_a_bookkeeping_write_adds_nothing_to_the_chat_context(store: SQLiteRelationalStore) -> None:
    manager = _manager(store, namespaces=["global"])
    chat_id = f"bookkeeping-{uuid4().hex}"
    chat_id_var.set(chat_id)
    deltas = get_shared_ephemeral_delta_store()

    await write_bookkeeping(manager, _KEY, "1")
    assert deltas.get_all_raw_deltas(chat_id) == []

    # Control: a profile write of the same manager in the same chat is announced to the model.
    await manager.set_profile_attribute("favorite_color", "teal")
    assert [item.target_key for item in deltas.get_all_raw_deltas(chat_id)] == ["profile:favorite_color"]
