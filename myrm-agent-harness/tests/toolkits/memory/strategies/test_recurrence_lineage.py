"""The recurrence buffer holds the opening words of sessions, so each row names its owner, scope and chat.

A detector reads only its own user's and scope's rows, a consolidated memory lists every chat that fed it, and a chat's
rows can be purged. Each case drives a real detector over an embedded Qdrant: a mock store would accept any filter and
show neither the isolation nor the purge.
"""

from __future__ import annotations

from uuid import uuid4

from myrm_agent_harness.toolkits.memory.strategies.recurrence import (
    RecurrenceDetector,
    buffer_collection,
    purge_recurrence_buffer,
)
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore

TOPIC = "How do I keep flaky pytest tests under control with retries and logging"


class _Embedder:
    """Every text lands on one vector, so rows of the same user and scope always count as recurrences."""

    dimension = 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.5, 0.5, 0.5]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


def detector_over(
    qdrant: QdrantVectorStore, prefix: str, *, user_id: str = "u1", namespace: str = "global", k: int = 3
) -> RecurrenceDetector:
    return RecurrenceDetector(
        embedding=_Embedder(),
        vector=qdrant,
        collection_prefix=prefix,
        user_id=user_id,
        primary_namespace=namespace,
        recurrence_k=k,
    )


async def rows(qdrant: QdrantVectorStore, prefix: str) -> list[tuple[str, str]]:
    """(owner, chat) of every row in the buffer in a stable order; the chat is empty for a row with no chat link."""
    docs, _ = await qdrant.scroll(buffer_collection(prefix), limit=100)
    return sorted((str(doc.metadata["user_id"]), str(doc.metadata.get("source_chat_id", ""))) for doc in docs)


async def test_a_row_records_its_owner_scope_and_chat(qdrant: QdrantVectorStore) -> None:
    prefix = f"rl{uuid4().hex[:8]}"

    await detector_over(qdrant, prefix, namespace="agent:x").check_recurrence(TOPIC, source_chat_id="chat-a")

    [doc], _ = await qdrant.scroll(buffer_collection(prefix), limit=10)
    assert (doc.metadata["user_id"], doc.metadata["primary_namespace"], doc.metadata["source_chat_id"]) == (
        "u1",
        "agent:x",
        "chat-a",
    )


async def test_a_session_without_a_chat_leaves_a_row_with_no_chat_link(qdrant: QdrantVectorStore) -> None:
    prefix = f"rl{uuid4().hex[:8]}"

    await detector_over(qdrant, prefix).check_recurrence(TOPIC, source_chat_id=None)

    assert await rows(qdrant, prefix) == [("u1", "")]
    assert await purge_recurrence_buffer(qdrant, prefix, user_id="u1", chat_id="") == 0


async def test_a_detector_counts_only_the_rows_of_its_own_user_and_scope(qdrant: QdrantVectorStore) -> None:
    prefix = f"rl{uuid4().hex[:8]}"
    for other in (detector_over(qdrant, prefix, user_id="u2"), detector_over(qdrant, prefix, namespace="agent:x")):
        for i in range(3):
            await other.check_recurrence(TOPIC, source_chat_id=f"theirs-{i}")
    mine = detector_over(qdrant, prefix)

    first = await mine.check_recurrence(TOPIC, source_chat_id="mine-0")
    second = await mine.check_recurrence(TOPIC, source_chat_id="mine-1")
    third = await mine.check_recurrence(TOPIC, source_chat_id="mine-2")

    assert [(r.triggered, r.recurrence_count) for r in (first, second, third)] == [(False, 1), (False, 2), (True, 3)]
    assert set(third.source_chat_ids) == {"mine-0", "mine-1", "mine-2"}


async def test_a_consolidated_memory_derives_from_the_current_chat_first_then_every_earlier_one(
    qdrant: QdrantVectorStore,
) -> None:
    prefix = f"rl{uuid4().hex[:8]}"
    detector = detector_over(qdrant, prefix)
    await detector.check_recurrence(TOPIC, source_chat_id="chat-a")
    await detector.check_recurrence(TOPIC, source_chat_id=None)

    triggered = await detector.check_recurrence(TOPIC, source_chat_id="chat-c")

    assert triggered.triggered
    assert triggered.source_chat_ids == ("chat-c", "chat-a")


async def test_a_must_remember_signal_derives_from_the_one_session_that_stated_it(qdrant: QdrantVectorStore) -> None:
    detector = detector_over(qdrant, f"rl{uuid4().hex[:8]}")

    result = await detector.check_recurrence("I have a severe allergy to penicillin", source_chat_id="chat-a")

    assert result.triggered and result.source_chat_ids == ()


async def test_purging_a_chat_deletes_only_its_rows_of_that_user(qdrant: QdrantVectorStore) -> None:
    prefix = f"rl{uuid4().hex[:8]}"
    mine, theirs = detector_over(qdrant, prefix, k=9), detector_over(qdrant, prefix, user_id="u2", k=9)
    await mine.check_recurrence(TOPIC, source_chat_id="chat-a")
    await mine.check_recurrence(TOPIC, source_chat_id="chat-b")
    await theirs.check_recurrence(TOPIC, source_chat_id="chat-a")

    assert await purge_recurrence_buffer(qdrant, prefix, user_id="u1", chat_id="chat-a") == 1

    assert await rows(qdrant, prefix) == [("u1", "chat-b"), ("u2", "chat-a")]


async def test_a_deprecated_row_is_purged_with_its_chat(qdrant: QdrantVectorStore) -> None:
    prefix = f"rl{uuid4().hex[:8]}"
    detector = detector_over(qdrant, prefix)
    for chat in ("chat-a", "chat-b", "chat-c"):
        await detector.check_recurrence(TOPIC, source_chat_id=chat)

    assert await purge_recurrence_buffer(qdrant, prefix, user_id="u1", chat_id="chat-a") == 1

    assert await rows(qdrant, prefix) == [("u1", "chat-b"), ("u1", "chat-c")]


async def test_purging_a_user_deletes_every_row_of_that_user_only(qdrant: QdrantVectorStore) -> None:
    prefix = f"rl{uuid4().hex[:8]}"
    for user_id, chat in (("u1", "chat-a"), ("u1", "chat-b"), ("u2", "chat-c")):
        await detector_over(qdrant, prefix, user_id=user_id, k=9).check_recurrence(TOPIC, source_chat_id=chat)

    assert await purge_recurrence_buffer(qdrant, prefix, user_id="u1") == 2

    assert await rows(qdrant, prefix) == [("u2", "chat-c")]


async def test_purging_a_buffer_that_was_never_created_deletes_nothing(qdrant: QdrantVectorStore) -> None:
    assert await purge_recurrence_buffer(qdrant, f"rl{uuid4().hex[:8]}", user_id="u1", chat_id="chat-a") == 0
