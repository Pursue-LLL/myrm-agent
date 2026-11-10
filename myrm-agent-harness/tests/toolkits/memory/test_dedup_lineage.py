"""A memory the deduplicator folds a newer one into derives from the chats of both, so the older chat's deletion reaches it.

The update runs on a memory read back from a real Qdrant, the way the writer applies a deduplication verdict.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.dedup_types import DeduplicatableMemory, DeduplicationDecision
from myrm_agent_harness.toolkits.memory.strategies.dedup_update import apply_dedup_update
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory
from tests.support.consolidation_seeds import GLOBAL, NewManager, episodic, seed, semantic


async def fold(manager: MemoryManager, existing_id: str, incoming: DeduplicatableMemory) -> DeduplicatableMemory:
    vector, _ = manager._vec()
    updated = await apply_dedup_update(
        incoming, existing_id, "merged text", DeduplicationDecision.UPDATE_MERGE, vector, manager.config
    )
    assert updated is not None and updated.id == existing_id
    return updated


async def test_a_semantic_update_keeps_the_chat_it_replaces_and_adds_the_newer_one(new_manager: NewManager) -> None:
    manager = new_manager()
    existing = semantic("User prefers Python", 1, source_chat_id="chat-a")
    await seed(manager, [existing])
    incoming = SemanticMemory(content="User prefers Python for data work", scope=GLOBAL, source_chat_id="chat-b")

    updated = await fold(manager, existing.id, incoming)

    assert updated.source_chat_id == "chat-b"
    assert sorted(updated.source_chat_ids) == ["chat-a", "chat-b"]


async def test_an_update_from_a_memory_without_a_chat_keeps_the_existing_lineage(new_manager: NewManager) -> None:
    manager = new_manager()
    existing = semantic("User prefers Python", 1, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"])
    await seed(manager, [existing])
    incoming = SemanticMemory(content="User prefers Python for data work", scope=GLOBAL)

    updated = await fold(manager, existing.id, incoming)

    assert updated.source_chat_id == "chat-b"
    assert sorted(updated.source_chat_ids) == ["chat-a", "chat-b"]


async def test_an_episodic_update_adds_the_newer_chat_too(new_manager: NewManager) -> None:
    manager = new_manager()
    existing = episodic("User asked about tea", 1, source_chat_id="chat-a")
    await seed(manager, [existing])
    incoming = EpisodicMemory(content="User asked about tea again", scope=GLOBAL, source_chat_id="chat-b")

    updated = await fold(manager, existing.id, incoming)

    assert updated.source_chat_id == "chat-b"
    assert sorted(updated.source_chat_ids) == ["chat-a", "chat-b"]
