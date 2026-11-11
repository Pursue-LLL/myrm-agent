"""A rule built from several chats goes with any of them, like every other memory derived from a chat.

A rule names the chat it was written from and, when several sources built it, every chat it derives from. Both links
live in the rule row and in the proposal that waits for approval, so the deletion cascade finds the rule and the
proposal through either chat. Real manager over an embedded Qdrant and SQLite.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.types import MemoryStatus, MemoryType, ProceduralMemory
from tests.support.consolidation_seeds import NewManager


def rule(
    action: str, *, source_chat_id: str | None = None, source_chat_ids: list[str] | None = None
) -> ProceduralMemory:
    return ProceduralMemory(
        content=f"Rule: {action}",
        trigger="the user asks for a spreadsheet",
        action=action,
        source_chat_id=source_chat_id,
        source_chat_ids=source_chat_ids or [],
    )


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {kind: count for kind, count in counts.items() if count}


async def test_a_rule_keeps_every_chat_it_was_built_from(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])

    stored = await manager.store(
        rule("produce an xlsx file", source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"]),
        _bypass_approval=True,
    )

    read_back = await manager._rel().get_rule(stored.id)
    assert read_back is not None
    assert (read_back.source_chat_id, read_back.source_chat_ids) == ("chat-b", ["chat-b", "chat-a"])
    assert "source_chat_id" not in read_back.metadata
    assert "source_chat_ids" not in read_back.metadata


async def test_a_rule_row_with_the_chat_in_its_plain_metadata_reads_back_with_the_chat_as_a_field(
    new_manager: NewManager,
) -> None:
    manager = new_manager(["agent:x"])
    stored = await manager.store(rule("produce an xlsx file"), _bypass_approval=True)
    stored.metadata["source_chat_id"] = "chat-a"
    await manager._rel().update_rule(stored.id, stored)

    read_back = await manager._rel().get_rule(stored.id)

    assert read_back is not None
    assert read_back.source_chat_id == "chat-a"
    assert "source_chat_id" not in read_back.metadata


async def test_a_rule_keeps_its_chats_when_it_is_edited_or_archived(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])
    stored = await manager.store(
        rule("produce an xlsx file", source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"]),
        _bypass_approval=True,
    )

    await manager.update_memory(stored.id, content="Rule: produce a csv file", metadata={"edited": "yes"})
    await manager.update_memory(stored.id, status=MemoryStatus.ARCHIVED)

    kept = await manager._rel().get_rule(stored.id)
    assert kept is not None
    assert (kept.content, kept.metadata.get("edited")) == ("Rule: produce a csv file", "yes")
    assert (kept.source_chat_id, kept.source_chat_ids) == ("chat-b", ["chat-b", "chat-a"])
    cascade = new_manager(all_scopes=True)
    assert await cascade.count_by_source_chat_id("chat-a") == {"procedural": 1}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {"procedural": 1}
    assert await manager._rel().get_rule(stored.id) is None


async def test_deleting_any_chat_a_rule_was_built_from_removes_it(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])
    built_from_a = await manager.store(
        rule("produce an xlsx file", source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"]),
        _bypass_approval=True,
    )
    written_in_a = await manager.store(rule("answer in French", source_chat_id="chat-a"), _bypass_approval=True)
    written_in_c = await manager.store(rule("quote sources", source_chat_id="chat-c"), _bypass_approval=True)
    cascade = new_manager(all_scopes=True)

    preview = await cascade.count_by_source_chat_id("chat-a")
    purged = await cascade.purge_by_source_chat_id("chat-a")

    assert preview == {"procedural": 2}
    assert nonzero(purged) == preview
    assert await manager._rel().get_rule(built_from_a.id) is None
    assert await manager._rel().get_rule(written_in_a.id) is None
    assert await manager._rel().get_rule(written_in_c.id) is not None


async def test_a_rule_built_from_chats_that_are_not_deleted_stays(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"])
    kept = await manager.store(
        rule("produce an xlsx file", source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-c"]),
        _bypass_approval=True,
    )
    cascade = new_manager(all_scopes=True)

    assert await cascade.count_by_source_chat_id("chat-a") == {}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {}
    assert await manager._rel().get_rule(kept.id) is not None


async def test_a_proposal_built_from_several_chats_is_discarded_with_any_of_them(new_manager: NewManager) -> None:
    manager = new_manager(["agent:x"], approval_required=True)
    await manager.store(rule("produce an xlsx file", source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"]))
    await manager.store(rule("quote sources", source_chat_id="chat-c"))
    cascade = new_manager(all_scopes=True)

    assert await cascade.count_by_source_chat_id("chat-a") == {"pending": 1}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {"pending": 1}
    assert [record.source_chat_id for record in await manager.list_pending()] == ["chat-c"]


async def test_an_approved_rule_and_its_resolved_proposal_go_with_any_chat_it_was_built_from(
    new_manager: NewManager,
) -> None:
    manager = new_manager(["agent:x"], approval_required=True)
    await manager.store(rule("produce an xlsx file", source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"]))
    [proposal] = await manager.list_pending()
    approved = await manager.approve(proposal.id)
    assert isinstance(approved, ProceduralMemory)
    cascade = new_manager(all_scopes=True)

    assert await cascade.count_by_source_chat_id("chat-a") == {"procedural": 1, "pending": 1}
    assert nonzero(await cascade.purge_by_source_chat_id("chat-a")) == {"procedural": 1, "pending": 1}
    assert await manager._rel().get_rule(approved.id) is None
    assert await manager.list_memories(MemoryType.PROCEDURAL) == []
