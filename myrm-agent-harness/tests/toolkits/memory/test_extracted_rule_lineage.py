"""A rule the extractor proposes records the chat it came from, so deleting that chat removes it too.

The proposal waits in the approval queue and, once approved, lives as a stored rule: both carry the chat link the
cascade looks for. Real manager over an embedded Qdrant and SQLite; the proposals go through the same persistence step
the extraction run uses.
"""

from __future__ import annotations

from myrm_agent_harness.agent._internals.memory_extraction import persist_extracted_memories
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.extractor import MemoryExtractor
from myrm_agent_harness.toolkits.memory.strategies.extractor.models import ExtractedMemory
from myrm_agent_harness.toolkits.memory.types import EvidenceReference, MemoryType, ProceduralMemory
from tests.support.consolidation_seeds import NewManager


def rule_from(chat_id: str, action: str = "produce an xlsx file") -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PROCEDURAL,
        content=f"Rule: {action}",
        confidence=0.95,
        importance=0.8,
        trigger="the user asks for a spreadsheet",
        action=action,
        evidence=[EvidenceReference(source_id=chat_id, message_id="m1", quote_snippet="always give me xlsx")],
    )


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {kind: count for kind, count in counts.items() if count}


async def approved_rule(manager: MemoryManager, chat_id: str, action: str) -> ProceduralMemory:
    await persist_extracted_memories([rule_from(chat_id, action)], manager, chat_id)
    [proposal] = [record for record in await manager.list_pending() if record.content == f"Rule: {action}"]
    rule = await manager.approve(proposal.id)
    assert isinstance(rule, ProceduralMemory)
    return rule


def test_a_proposed_rule_names_its_chat_in_its_metadata() -> None:
    [rule] = MemoryExtractor().to_concrete_memories([rule_from("chat-a")], source_chat_id="chat-a")

    assert isinstance(rule, ProceduralMemory)
    assert rule.metadata["source_chat_id"] == "chat-a"


def test_a_rule_proposed_outside_any_chat_names_none() -> None:
    [rule] = MemoryExtractor().to_concrete_memories([rule_from("chat-a")])

    assert isinstance(rule, ProceduralMemory)
    assert "source_chat_id" not in rule.metadata


async def test_deleting_a_chat_discards_the_rule_proposed_from_it(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])
    await persist_extracted_memories([rule_from("chat-a")], manager, "chat-a")
    cascade = new_manager(all_scopes=True)

    assert [record.source_chat_id for record in await manager.list_pending()] == ["chat-a"]
    assert await cascade.count_by_source_chat_id("chat-a") == {"pending": 1}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {"pending": 1}
    assert await manager.list_pending() == []


async def test_deleting_a_chat_removes_the_rule_approved_from_it(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])
    rule = await approved_rule(manager, "chat-a", "produce an xlsx file")
    cascade = new_manager(all_scopes=True)

    # The resolved approval record keeps the rule's text, so it goes with the chat as well.
    assert await cascade.count_by_source_chat_id("chat-a") == {"procedural": 1, "pending": 1}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {"procedural": 1, "pending": 1}
    assert await manager._rel().get_rule(rule.id) is None


async def test_deleting_a_chat_keeps_the_rules_of_other_chats(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])
    removed = await approved_rule(manager, "chat-a", "produce an xlsx file")
    kept = await approved_rule(manager, "chat-b", "produce a csv file")
    cascade = new_manager(all_scopes=True)

    await cascade.purge_by_source_chat_id("chat-a")

    assert await manager._rel().get_rule(removed.id) is None
    assert await manager._rel().get_rule(kept.id) is not None
