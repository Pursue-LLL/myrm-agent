"""The deleted-chat fence refuses writes derived from a chat the memory system saw deleted, for a while, per user.

The registry is plain process state, so each case drives it directly and moves its clock by hand; the writers that
consult it are tested against real stores in ``test_deleted_chat_writes.py``.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument
from myrm_agent_harness.toolkits.memory.strategies import chat_fence
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import (
    clear_closed_chats,
    close_chat,
    derives_from_deleted_chat,
    document_derives_from_deleted_chat,
    is_closed,
    keep_live,
    keep_live_documents,
    reopen_chats,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

FIFTEEN_MINUTES = 15 * 60.0


class Clock:
    """The registry's time source, moved by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    moved = Clock()
    monkeypatch.setattr(chat_fence, "time", moved)
    return moved


def fact(content: str, chat_id: str | None = None, *, built_from: tuple[str, ...] = ()) -> SemanticMemory:
    return SemanticMemory(content=content, user_id="u1", source_chat_id=chat_id, source_chat_ids=list(built_from))


def test_a_closed_chat_is_refused_to_its_owner_only() -> None:
    close_chat("u1", "chat-a")

    assert is_closed("u1", "chat-a")
    assert not is_closed("u2", "chat-a")
    assert not is_closed("u1", "chat-b")


def test_a_chat_is_refused_for_fifteen_minutes_then_accepted(clock: Clock) -> None:
    close_chat("u1", "chat-a")

    clock.now += FIFTEEN_MINUTES - 1
    assert is_closed("u1", "chat-a")
    clock.now += 1
    assert not is_closed("u1", "chat-a")


def test_deleting_a_chat_again_extends_the_refusal(clock: Clock) -> None:
    close_chat("u1", "chat-a")
    clock.now += FIFTEEN_MINUTES / 2
    close_chat("u1", "chat-a")

    clock.now += FIFTEEN_MINUTES - 1
    assert is_closed("u1", "chat-a")


def test_closing_a_chat_drops_the_chats_whose_refusal_lapsed(clock: Clock) -> None:
    close_chat("u1", "chat-a")
    clock.now += FIFTEEN_MINUTES
    close_chat("u1", "chat-b")

    assert list(chat_fence._closed_until) == [("u1", "chat-b")]


def test_reopening_lifts_the_named_chats_of_that_user_only() -> None:
    for owner, chat in (("u1", "chat-a"), ("u1", "chat-b"), ("u2", "chat-a")):
        close_chat(owner, chat)

    reopen_chats("u1", ["chat-a", "never-closed"])

    assert not is_closed("u1", "chat-a")
    assert is_closed("u1", "chat-b")
    assert is_closed("u2", "chat-a")


def test_clearing_forgets_every_chat_of_every_user() -> None:
    close_chat("u1", "chat-a")
    close_chat("u2", "chat-b")

    clear_closed_chats()

    assert not is_closed("u1", "chat-a")
    assert not is_closed("u2", "chat-b")


@pytest.mark.parametrize(
    ("memory", "refused"),
    [
        (fact("written from the chat", "chat-a"), True),
        (fact("built from it among others", "chat-b", built_from=("chat-b", "chat-a")), True),
        (fact("built from other chats", "chat-b", built_from=("chat-b", "chat-c")), False),
        (fact("written outside any chat"), False),
    ],
    ids=["primary-link", "built-from-link", "other-chats", "no-chat"],
)
def test_a_memory_derives_from_a_closed_chat_through_either_chat_link(memory: SemanticMemory, refused: bool) -> None:
    close_chat("u1", "chat-a")

    assert derives_from_deleted_chat("u1", memory) is refused


def test_a_closed_chat_of_one_user_does_not_refuse_the_memory_of_another() -> None:
    close_chat("u1", "chat-a")

    assert not derives_from_deleted_chat("u2", fact("written from the chat", "chat-a"))


def test_keep_live_drops_only_what_derives_from_a_closed_chat_and_keeps_the_order() -> None:
    close_chat("u1", "chat-a")
    first, gone, built_from_it, last = (
        fact("first", "chat-b"),
        fact("gone", "chat-a"),
        fact("merged", "chat-b", built_from=("chat-b", "chat-a")),
        fact("last", "chat-c", built_from=("chat-c",)),
    )

    assert keep_live("u1", [first, gone, built_from_it, last]) == [first, last]


def test_keep_live_returns_every_memory_when_no_chat_is_closed() -> None:
    memories = [fact("one", "chat-a"), fact("two", "chat-b")]

    live = keep_live("u1", memories)

    assert live == memories
    assert live is not memories


def stored(
    doc_id: str, chat_id: str | None = None, *, built_from: object = None, user_id: str = "u1"
) -> VectorDocument:
    metadata: dict[str, object] = {"user_id": user_id}
    if chat_id is not None:
        metadata["source_chat_id"] = chat_id
    if built_from is not None:
        metadata["source_chat_ids"] = built_from
    return VectorDocument(id=doc_id, content=doc_id, metadata=metadata)


@pytest.mark.parametrize(
    ("document", "refused"),
    [
        (stored("written", "chat-a"), True),
        (stored("built", "chat-b", built_from=["chat-b", "chat-a"]), True),
        (stored("other-chats", "chat-b", built_from=["chat-b", "chat-c"]), False),
        (stored("no-chat"), False),
        (stored("not-a-list", "chat-b", built_from="chat-a"), False),
        (stored("another-user", "chat-a", user_id="u2"), False),
    ],
    ids=["primary-link", "built-from-link", "other-chats", "no-chat", "malformed-list", "another-user"],
)
def test_a_stored_document_derives_from_a_closed_chat_through_either_chat_link(
    document: VectorDocument, refused: bool
) -> None:
    close_chat("u1", "chat-a")

    assert document_derives_from_deleted_chat(document) is refused


def test_keep_live_documents_drops_only_what_derives_from_a_closed_chat_and_keeps_the_order() -> None:
    close_chat("u1", "chat-a")
    first, gone, built_from_it, last = (
        stored("first", "chat-b"),
        stored("gone", "chat-a"),
        stored("merged", "chat-b", built_from=["chat-b", "chat-a"]),
        stored("last"),
    )

    assert keep_live_documents([first, gone, built_from_it, last]) == [first, last]


def test_keep_live_documents_returns_every_document_when_no_chat_is_closed() -> None:
    documents = [stored("one", "chat-a"), stored("two", "chat-b")]

    assert keep_live_documents(documents) == documents
