"""The ledger of what the next wake turn answers and what the agent already read of it."""

from __future__ import annotations

from app.services.agent.adaptive_wakeup import settled_results
from app.services.agent.adaptive_wakeup.settled_results import SettledResults


def test_a_wake_turn_whose_every_result_was_read_is_all_read() -> None:
    ledger = SettledResults()
    ledger.queue("chat", "task-1")
    ledger.queue("chat", "task-2")
    ledger.mark_read("chat", ["task-1", "task-2", "unrelated"])

    assert ledger.take_all_read("chat")


def test_one_unread_result_keeps_the_wake_turn() -> None:
    ledger = SettledResults()
    ledger.queue("chat", "task-1")
    ledger.queue("chat", "task-2")
    ledger.mark_read("chat", ["task-1"])

    assert not ledger.take_all_read("chat")


def test_a_wake_turn_with_nothing_queued_is_never_all_read() -> None:
    ledger = SettledResults()
    ledger.mark_read("chat", ["task-1"])

    assert not ledger.take_all_read("chat")


def test_a_read_that_lands_before_its_settlement_still_counts() -> None:
    ledger = SettledResults()
    ledger.mark_read("chat", ["task-1"])
    ledger.queue("chat", "task-1")

    assert ledger.take_all_read("chat")


def test_taking_the_chat_clears_the_queue_and_the_marks_it_answered() -> None:
    ledger = SettledResults()
    ledger.queue("chat", "task-1")
    ledger.mark_read("chat", ["task-1", "kept"])
    ledger.take_all_read("chat")

    # The next wake turn answers only what settled after it: the old mark does not carry over to a new settlement.
    ledger.queue("chat", "task-1")
    assert not ledger.take_all_read("chat")
    ledger.queue("chat", "kept")
    assert ledger.take_all_read("chat")


def test_chats_do_not_share_results() -> None:
    ledger = SettledResults()
    ledger.queue("a", "task-1")
    ledger.mark_read("b", ["task-1"])

    assert not ledger.take_all_read("a")


def test_a_chat_that_reads_more_than_the_cap_forgets_the_oldest_marks(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settled_results, "_MAX_READ_PER_CHAT", 3)
    ledger = SettledResults()
    ledger.mark_read("chat", ["t1", "t2", "t3", "t4"])
    ledger.queue("chat", "t1")
    assert not ledger.take_all_read("chat")

    ledger.queue("chat", "t4")
    assert ledger.take_all_read("chat")


def test_reading_a_result_again_keeps_it_among_the_newest(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settled_results, "_MAX_READ_PER_CHAT", 2)
    ledger = SettledResults()
    ledger.mark_read("chat", ["t1", "t2"])
    ledger.mark_read("chat", ["t1", "t3"])

    ledger.queue("chat", "t1")
    assert ledger.take_all_read("chat")


def test_forgetting_a_chat_drops_both_sides() -> None:
    ledger = SettledResults()
    ledger.queue("chat", "task-1")
    ledger.mark_read("chat", ["task-1"])

    ledger.forget("chat")

    ledger.queue("chat", "task-1")
    assert not ledger.take_all_read("chat")
