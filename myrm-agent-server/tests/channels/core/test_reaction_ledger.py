"""ReactionLedger remembers what a channel added so an empty emoji can undo exactly that."""

from __future__ import annotations

from app.channels.core.reaction_ledger import ReactionLedger


def test_take_returns_what_was_remembered_once() -> None:
    ledger = ReactionLedger()
    ledger.remember("chat", "m1", "eyes")
    assert ledger.take("chat", "m1") == "eyes"
    assert ledger.take("chat", "m1") is None


def test_nothing_is_taken_for_a_message_that_was_never_reacted_to() -> None:
    assert ReactionLedger().take("chat", "m1") is None


def test_the_same_message_id_in_another_chat_is_a_different_entry() -> None:
    ledger = ReactionLedger()
    ledger.remember("chat-a", "m1", "eyes")
    assert ledger.take("chat-b", "m1") is None
    assert ledger.take("chat-a", "m1") == "eyes"


def test_a_later_reaction_replaces_the_earlier_one() -> None:
    ledger = ReactionLedger()
    ledger.remember("chat", "m1", "eyes")
    ledger.remember("chat", "m1", "white_check_mark")
    assert ledger.take("chat", "m1") == "white_check_mark"


def test_the_oldest_entry_is_dropped_when_the_ledger_is_full() -> None:
    ledger = ReactionLedger(max_entries=2)
    ledger.remember("chat", "m1", "a")
    ledger.remember("chat", "m2", "b")
    ledger.remember("chat", "m3", "c")
    assert ledger.take("chat", "m1") is None
    assert ledger.take("chat", "m2") == "b"
    assert ledger.take("chat", "m3") == "c"


def test_a_refreshed_entry_survives_eviction() -> None:
    ledger = ReactionLedger(max_entries=2)
    ledger.remember("chat", "m1", "a")
    ledger.remember("chat", "m2", "b")
    ledger.remember("chat", "m1", "a2")
    ledger.remember("chat", "m3", "c")
    assert ledger.take("chat", "m1") == "a2"
    assert ledger.take("chat", "m2") is None
