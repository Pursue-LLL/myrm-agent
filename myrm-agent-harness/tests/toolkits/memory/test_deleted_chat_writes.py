"""A writer that outlives the deletion of its chat may not bring back what the deletion purged.

Post-turn extraction, a session flush, a dedup merge, a proposal and a recurrence check each run for seconds, so one can
still be running when the user deletes the chat it derives from. Every case drives real managers over SQLite and one
embedded Qdrant: the chat is deleted the way the app deletes it (``purge_by_source_chat_id`` over every scope), either
before the writer starts or in the middle of one of its steps, and what the writer left behind is read back from the
stores.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

import pytest

from myrm_agent_harness.agent._internals.memory_extraction import persist_extracted_memories
from myrm_agent_harness.toolkits.memory._internal.storage import MemoryRejectedError
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import DELETED_CHAT_REJECTION
from myrm_agent_harness.toolkits.memory.strategies.extractor.models import ExtractedMemory
from myrm_agent_harness.toolkits.memory.strategies.recurrence import RecurrenceDetector, buffer_collection
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    EpisodicMemory,
    EvidenceReference,
    MemoryType,
    SemanticMemory,
)
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore
from tests.support.consolidation_seeds import NewManager, episodic, semantic

TOPIC = "How do I keep flaky pytest tests under control with retries and logging"


async def delete_chat(new_manager: NewManager, chat_id: str) -> None:
    """What the chat-deletion endpoint does: purge everything derived from the chat, in every scope."""
    await new_manager(all_scopes=True).purge_by_source_chat_id(chat_id)


def fact_from(chat_id: str) -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.SEMANTIC,
        content="The user prefers green tea",
        confidence=0.95,
        importance=0.8,
        evidence=[EvidenceReference(source_id=chat_id, message_id="m1", quote_snippet="I only drink green tea")],
    )


def rule_from(chat_id: str) -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PROCEDURAL,
        content="Rule: produce an xlsx file",
        confidence=0.95,
        importance=0.8,
        trigger="the user asks for a spreadsheet",
        action="produce an xlsx file",
        evidence=[EvidenceReference(source_id=chat_id, message_id="m1", quote_snippet="always give me xlsx")],
    )


class ProbeEmbedder:
    """Counts its calls and, when given a step, runs it once during the first call."""

    dimension = 4

    def __init__(self, during_first_call: Callable[[], Awaitable[None]] | None = None) -> None:
        self.calls = 0
        self._during_first_call = during_first_call

    async def embed(self, text: str) -> list[float]:
        self.calls += 1
        if self.calls == 1 and self._during_first_call is not None:
            await self._during_first_call()
        return [1.0, 0.5, 0.5, 0.5]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


async def buffer_rows(qdrant: QdrantVectorStore, manager: MemoryManager) -> list[tuple[str, str]]:
    """(owner, chat) of every row in the recurrence buffer, in a stable order."""
    docs, _ = await qdrant.scroll(buffer_collection(manager.config.collection_prefix), limit=100)
    return sorted((str(doc.metadata["user_id"]), str(doc.metadata.get("source_chat_id", ""))) for doc in docs)


# -- Direct writes ------------------------------------------------------------------------------------------------


async def test_a_memory_saved_after_its_chat_was_deleted_is_refused_with_the_reason(new_manager: NewManager) -> None:
    manager = new_manager()
    await delete_chat(new_manager, "chat-a")

    with pytest.raises(MemoryRejectedError) as refused:
        await manager.store(semantic("User prefers tea", 0, source_chat_id="chat-a"), _bypass_approval=True)

    assert str(refused.value) == DELETED_CHAT_REJECTION
    assert await manager.count_by_source_chat_id("chat-a") == {}


async def test_a_memory_built_from_a_deleted_chat_among_others_is_refused(new_manager: NewManager) -> None:
    manager = new_manager()
    await delete_chat(new_manager, "chat-a")
    merged = semantic("User prefers tea", 0, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"])

    with pytest.raises(MemoryRejectedError):
        await manager.store(merged, _bypass_approval=True)

    assert await manager.count_by_source_chat_id("chat-b") == {}


async def test_other_chats_and_other_users_are_not_refused(new_manager: NewManager) -> None:
    await delete_chat(new_manager, "chat-a")
    mine, theirs = new_manager(), new_manager(user_id="u2")

    await mine.store(semantic("User prefers tea", 0, source_chat_id="chat-b"), _bypass_approval=True)
    await theirs.store(SemanticMemory(content="User prefers coffee", user_id="u2", source_chat_id="chat-a"))

    assert await mine.count_by_source_chat_id("chat-b") == {"semantic": 1}
    assert await theirs.count_by_source_chat_id("chat-a") == {"semantic": 1}


async def test_a_batch_loses_only_the_memories_derived_from_the_deleted_chat(new_manager: NewManager) -> None:
    manager = new_manager()
    await delete_chat(new_manager, "chat-a")
    batch = [
        semantic("Prefers tea", 0, source_chat_id="chat-a"),
        semantic("Prefers a quiet desk", 1, source_chat_id="chat-b"),
        semantic("Works from Lisbon", 2, source_chat_id="chat-c", source_chat_ids=["chat-c", "chat-a"]),
        semantic("Reads on the train", 3),
    ]

    stored = await manager.store_batch(batch, _bypass_approval=True)

    assert sorted(memory.content for memory in stored) == ["Prefers a quiet desk", "Reads on the train"]
    assert await manager.count_by_source_chat_id("chat-a") == {}
    assert await manager.count_by_source_chat_id("chat-c") == {}


@pytest.mark.parametrize(
    ("dedup_step", "build"),
    [("_deduplicate_semantic_batch", semantic), ("_deduplicate_episodic_batch", episodic)],
    ids=["semantic", "episodic"],
)
async def test_a_dedup_merge_that_folds_in_a_chat_deleted_meanwhile_is_not_stored(
    new_manager: NewManager,
    monkeypatch: pytest.MonkeyPatch,
    dedup_step: str,
    build: Callable[..., SemanticMemory | EpisodicMemory],
) -> None:
    manager = new_manager()
    merged = build("User prefers green tea", 1, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"])

    async def merge_while_chat_a_is_deleted(memories: Sequence[AnyMemory]) -> list[AnyMemory]:
        await delete_chat(new_manager, "chat-a")
        return [merged]

    monkeypatch.setattr(manager._writer, dedup_step, merge_while_chat_a_is_deleted)

    stored = await manager.store_batch([build("User prefers tea", 0, source_chat_id="chat-b")])

    assert stored == []
    assert await manager.count_by_source_chat_id("chat-b") == {}
    assert await manager.count_by_source_chat_id("chat-a") == {}


# -- Session flush --------------------------------------------------------------------------------------------------


async def test_a_session_flushes_what_it_buffered_for_a_chat_that_is_still_there(new_manager: NewManager) -> None:
    manager = new_manager()
    session = manager.begin_session("chat-b")
    session.add_knowledge("User prefers green tea")
    session.add_rule("the user asks for a spreadsheet", "produce an xlsx file")

    assert len(await manager.end_session()) == 2
    assert await manager.count_by_source_chat_id("chat-b") == {"semantic": 1, "procedural": 1}


async def test_a_session_does_not_flush_what_it_buffered_for_a_chat_deleted_before_it_ended(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    session = manager.begin_session("chat-a")
    session.add_knowledge("User prefers green tea")
    session.add_rule("the user asks for a spreadsheet", "produce an xlsx file")
    await delete_chat(new_manager, "chat-a")

    assert await manager.end_session() == []
    assert await manager.count_by_source_chat_id("chat-a") == {}


# -- Post-turn extraction -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("force_pending", [True, False], ids=["proposed-for-review", "stored-directly"])
async def test_extraction_finishing_after_its_chat_was_deleted_keeps_nothing(
    new_manager: NewManager, force_pending: bool
) -> None:
    manager = new_manager(["agent:x"])
    await delete_chat(new_manager, "chat-a")

    kept = await persist_extracted_memories(
        [fact_from("chat-a"), rule_from("chat-a")], manager, "chat-a", force_pending=force_pending
    )

    assert kept == 0
    assert await manager.list_pending() == []
    assert await new_manager(all_scopes=True).count_by_source_chat_id("chat-a") == {}


@pytest.mark.parametrize(
    ("force_pending", "kept_in"),
    [(True, {"pending": 2}), (False, {"semantic": 1, "procedural": 1})],
    ids=["proposed-for-review", "stored-directly"],
)
async def test_extraction_for_a_chat_that_is_still_there_keeps_what_it_extracted(
    new_manager: NewManager, force_pending: bool, kept_in: dict[str, int]
) -> None:
    manager = new_manager(["agent:x"])
    await delete_chat(new_manager, "chat-a")

    await persist_extracted_memories(
        [fact_from("chat-b"), rule_from("chat-b")], manager, "chat-b", force_pending=force_pending
    )

    assert await new_manager(all_scopes=True).count_by_source_chat_id("chat-b") == kept_in


# -- Proposals ------------------------------------------------------------------------------------------------------


async def test_a_proposal_derived_from_a_deleted_chat_is_not_queued(new_manager: NewManager) -> None:
    manager = new_manager()
    assert await manager.submit_pending(semantic("Prefers tea", 0, source_chat_id="chat-b")) != ""
    await delete_chat(new_manager, "chat-a")

    own = semantic("Prefers coffee", 1, source_chat_id="chat-a")
    built_from = semantic("Prefers cocoa", 2, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-a"])

    assert await manager.submit_pending(own) == ""
    assert await manager.submit_pending(built_from) == ""
    assert [record.source_chat_id for record in await manager.list_pending()] == ["chat-b"]


# -- Recurrence check -----------------------------------------------------------------------------------------------


async def test_a_summary_of_a_deleted_chat_costs_no_embedding_and_leaves_no_row(
    new_manager: NewManager, qdrant: QdrantVectorStore
) -> None:
    embedder = ProbeEmbedder()
    manager = new_manager(embedding=embedder)
    await manager.check_session_recurrence(TOPIC, source_chat_id="chat-b")
    embedded = embedder.calls
    await delete_chat(new_manager, "chat-a")

    await manager.check_session_recurrence(TOPIC, source_chat_id="chat-a")
    await manager.check_session_recurrence("I have a severe allergy to penicillin", source_chat_id="chat-a")

    assert embedder.calls == embedded
    assert await buffer_rows(qdrant, manager) == [("u1", "chat-b")]
    assert await manager.count_by_source_chat_id("chat-a") == {}


async def test_a_summary_embedded_while_its_chat_is_deleted_is_not_buffered(
    new_manager: NewManager, qdrant: QdrantVectorStore
) -> None:
    embedder = ProbeEmbedder(during_first_call=lambda: delete_chat(new_manager, "chat-a"))
    manager = new_manager(embedding=embedder)

    await manager.check_session_recurrence(TOPIC, source_chat_id="chat-a")

    assert await buffer_rows(qdrant, manager) == []


async def test_a_consolidation_that_folds_in_a_chat_deleted_mid_check_is_not_stored_and_its_row_stays_gone(
    new_manager: NewManager, qdrant: QdrantVectorStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    for chat in ("chat-1", "chat-2", "chat-3"):
        await manager.check_session_recurrence(TOPIC, source_chat_id=chat)
    evict = RecurrenceDetector._evict_old_entries

    async def evict_after_chat_2_is_deleted(detector: RecurrenceDetector) -> None:
        await delete_chat(new_manager, "chat-2")
        await evict(detector)

    monkeypatch.setattr(RecurrenceDetector, "_evict_old_entries", evict_after_chat_2_is_deleted)

    await manager.check_session_recurrence(TOPIC, source_chat_id="chat-4")

    assert await manager.count_by_source_chat_id("chat-4") == {}
    assert await buffer_rows(qdrant, manager) == [("u1", "chat-1"), ("u1", "chat-3"), ("u1", "chat-4")]


# -- Import ---------------------------------------------------------------------------------------------------------


async def test_importing_the_memories_of_a_deleted_chat_brings_them_back_on_purpose(new_manager: NewManager) -> None:
    manager = new_manager()
    await manager.store(semantic("User prefers tea", 0, source_chat_id="chat-a"), _bypass_approval=True)
    backup = await manager.export_all()
    await delete_chat(new_manager, "chat-a")

    assert await manager.import_memories(backup) == {"semantic": 1}
    await manager.store(semantic("User prefers green tea", 1, source_chat_id="chat-a"), _bypass_approval=True)

    assert await manager.count_by_source_chat_id("chat-a") == {"semantic": 2}
