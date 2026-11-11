"""A chat's deletion reaches what the chat produced under every scope of its user.

The cascade that runs when a chat is deleted cannot know which agent, channel or project scope wrote a memory, so it
runs on a manager that owns every scope. A manager of one scope still leaves the memories of the others alone, and no
manager reaches another user's memories. Real manager over an embedded Qdrant and SQLite.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemoryScope,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
)
from tests.support.consolidation_seeds import NewManager, episodic, seed, semantic

AGENT = MemoryScope(primary_namespace="agent:x", namespaces=["agent:x"])


def in_agent_scope[M: SemanticMemory | EpisodicMemory](memory: M, *, user_id: str = "u1") -> M:
    return memory.model_copy(update={"scope": AGENT, "user_id": user_id})


def rule_of_chat(chat_id: str) -> ProceduralMemory:
    return ProceduralMemory(
        content="Deliver spreadsheets as xlsx",
        trigger="the user asks for a spreadsheet",
        action="produce an xlsx file",
        source_chat_id=chat_id,
    )


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {kind: count for kind, count in counts.items() if count}


async def test_a_manager_of_every_scope_counts_and_purges_what_an_agent_scope_wrote(new_manager: NewManager) -> None:
    told_in_a = in_agent_scope(semantic("fact told in chat a", 1, source_chat_id="chat-a"))
    drawn_from_a = in_agent_scope(
        episodic("event drawn from chats b and a", 2, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"])
    )
    told_in_a_globally = semantic("fact told in chat a under the global scope", 3, source_chat_id="chat-a")
    told_in_c = in_agent_scope(semantic("fact told in chat c", 4, source_chat_id="chat-c"))
    agent = new_manager(["agent:x"])
    await seed(agent, [told_in_a, drawn_from_a, told_in_a_globally, told_in_c])
    rule = await agent.store(rule_of_chat("chat-a"), _bypass_approval=True)
    cascade = new_manager(all_scopes=True)

    preview = await cascade.count_by_source_chat_id("chat-a")
    purged = await cascade.purge_by_source_chat_id("chat-a")

    assert preview == {"semantic": 2, "episodic": 1, "procedural": 1}
    assert nonzero(purged) == preview
    assert [memory.id for memory in await agent.list_memories(MemoryType.SEMANTIC)] == [told_in_c.id]
    assert await agent.list_memories(MemoryType.EPISODIC) == []
    assert await agent._rel().get_rule(rule.id) is None


async def test_a_manager_of_one_scope_leaves_the_memories_of_another_scope(new_manager: NewManager) -> None:
    note = in_agent_scope(semantic("fact told in chat a", 1, source_chat_id="chat-a"))
    agent = new_manager(["agent:x"])
    await seed(agent, [note])
    rule = await agent.store(rule_of_chat("chat-a"), _bypass_approval=True)
    global_manager = new_manager()

    assert await global_manager.count_by_source_chat_id("chat-a") == {}
    assert nonzero(await global_manager.purge_by_source_chat_id("chat-a")) == {}
    assert [memory.id for memory in await agent.list_memories(MemoryType.SEMANTIC)] == [note.id]
    assert await agent._rel().get_rule(rule.id) is not None


async def test_a_manager_of_every_scope_leaves_the_memories_of_another_user(new_manager: NewManager) -> None:
    theirs = in_agent_scope(semantic("their fact told in chat a", 1, source_chat_id="chat-a"), user_id="u2")
    owner = new_manager(["agent:x"], user_id="u2")
    await seed(owner, [theirs])
    cascade = new_manager(all_scopes=True)

    assert await cascade.count_by_source_chat_id("chat-a") == {}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {}
    assert [memory.id for memory in await owner.list_memories(MemoryType.SEMANTIC)] == [theirs.id]
