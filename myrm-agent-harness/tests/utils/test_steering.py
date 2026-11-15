"""Tests for myrm_agent_harness.utils.runtime.steering."""

import threading

from myrm_agent_harness.utils.runtime.steering import (
    SteeringToken,
    get_steering_token,
    set_steering_token,
)


def test_steer_queues_messages() -> None:
    t = SteeringToken()
    t.steer("a")
    t.steer("b")
    assert t.has_pending is True


def test_has_pending_empty_queue() -> None:
    t = SteeringToken()
    assert t.has_pending is False


def test_is_active_and_steering_applied_before_activate() -> None:
    t = SteeringToken()
    assert t.is_active is False
    assert t.steering_applied is False


def test_activate_returns_messages_sets_flags() -> None:
    t = SteeringToken()
    t.steer("x")
    msgs = t.activate()
    assert msgs == ["x"]
    assert t.is_active is True
    assert t.steering_applied is True
    assert t.has_pending is False


def test_activate_second_call_returns_empty() -> None:
    t = SteeringToken()
    t.steer("one")
    assert t.activate() == ["one"]
    t.steer("late")
    assert t.activate() == []


def test_activate_empty_queue_returns_empty() -> None:
    t = SteeringToken()
    assert t.activate() == []


def test_collect_all_merges_activated_and_queue() -> None:
    t = SteeringToken()
    t.steer("first")
    assert t.activate() == ["first"]
    t.steer("second")
    assert t.collect_all_steering_messages() == ["first", "second"]


def test_reset_turn_clears_flags_keeps_every_undelivered_message_in_arrival_order() -> None:
    """A pass restarted by error recovery never collected what the last pass's tools activated."""
    t = SteeringToken()
    t.steer("q1")
    t.activate()
    t.steer("q2")
    t.reset_turn()
    assert t.is_active is False
    assert t.steering_applied is False
    assert t.has_pending is True
    assert t.collect_all_steering_messages() == ["q1", "q2"]


def test_reset_turn_after_collection_has_nothing_left_to_redeliver() -> None:
    t = SteeringToken()
    t.steer("q1")
    t.activate()
    assert t.collect_all_steering_messages() == ["q1"]
    t.reset_turn()
    assert t.has_pending is False
    assert t.collect_all_steering_messages() == []


def test_steer_and_redirect_report_that_the_run_took_the_message() -> None:
    t = SteeringToken()
    assert t.steer("a") is True
    assert t.redirect("b") is True


def test_close_if_idle_refuses_every_later_message() -> None:
    t = SteeringToken()
    assert t.close_if_idle() is True
    assert t.steer("late") is False
    assert t.redirect("later") is False
    assert t.has_pending is False
    assert t.redirect_requested is False
    assert t.collect_all_steering_messages() == []


def test_close_if_idle_keeps_the_token_open_while_a_message_waits() -> None:
    t = SteeringToken()
    t.steer("waiting")
    assert t.close_if_idle() is False
    assert t.steer("still accepted") is True
    assert t.collect_all_steering_messages() == ["waiting", "still accepted"]
    assert t.close_if_idle() is True


def test_close_if_idle_counts_an_activated_message_as_waiting() -> None:
    t = SteeringToken()
    t.steer("x")
    t.activate()
    assert t.close_if_idle() is False
    assert t.collect_all_steering_messages() == ["x"]
    assert t.close_if_idle() is True


def _race_a_close_against_senders() -> tuple[list[str], list[str]]:
    """Four threads steer while the main thread drains-or-closes the way a finishing run does."""
    token = SteeringToken()
    accepted: list[str] = []
    delivered: list[str] = []
    first_accepted = threading.Event()

    def sender(worker: int) -> None:
        for i in range(40):
            message = f"{worker}-{i}"
            if token.steer(message):
                accepted.append(message)
                first_accepted.set()

    senders = [threading.Thread(target=sender, args=(worker,)) for worker in range(4)]
    for s in senders:
        s.start()
    first_accepted.wait()
    while not token.close_if_idle():
        delivered.extend(token.collect_all_steering_messages())
    for s in senders:
        s.join()
    return accepted, delivered


def test_every_accepted_message_is_collected_whatever_races_the_close() -> None:
    """Accepted ⇒ delivered: no message can slip in between the last collection and the close."""
    for _ in range(25):
        accepted, delivered = _race_a_close_against_senders()
        assert accepted, "the race needs at least one accepted message to mean anything"
        assert sorted(delivered) == sorted(accepted)


def test_close_and_drain_returns_every_unread_message_in_receiving_order() -> None:
    t = SteeringToken()
    t.steer("first")
    t.activate()
    t.steer("second")
    t.redirect("third")
    assert t.close_and_drain() == ["first", "second", "third"]
    assert t.has_pending is False
    assert t.redirect_requested is False
    assert t.collect_all_steering_messages() == []


def test_close_and_drain_refuses_every_later_message() -> None:
    t = SteeringToken()
    t.steer("unread")
    t.close_and_drain()
    assert t.steer("late") is False
    assert t.redirect("later") is False
    assert t.close_and_drain() == []
    assert t.close_if_idle() is True


def test_close_and_drain_of_an_idle_token_returns_nothing() -> None:
    t = SteeringToken()
    assert t.close_and_drain() == []
    assert t.steer("late") is False


def test_close_and_drain_after_the_gate_has_nothing_left_to_hand_back() -> None:
    """A turn that completed through the gate leaves nothing for its owner to return."""
    t = SteeringToken()
    t.steer("read at the gate")
    assert t.close_if_idle() is False
    assert t.collect_all_steering_messages() == ["read at the gate"]
    assert t.close_if_idle() is True
    assert t.close_and_drain() == []


def _race_a_teardown_against_senders() -> tuple[list[str], list[str], list[str]]:
    """Four threads steer while the main thread reads once and then tears the token down the way an aborted run does."""
    token = SteeringToken()
    accepted: list[str] = []
    first_accepted = threading.Event()

    def sender(worker: int) -> None:
        for i in range(40):
            message = f"{worker}-{i}"
            if token.steer(message):
                accepted.append(message)
                first_accepted.set()

    senders = [threading.Thread(target=sender, args=(worker,)) for worker in range(4)]
    for s in senders:
        s.start()
    first_accepted.wait()
    read = token.collect_all_steering_messages()
    handed_back = token.close_and_drain()
    for s in senders:
        s.join()
    return accepted, read, handed_back


def test_every_accepted_message_is_read_or_handed_back_whatever_races_the_teardown() -> None:
    """Accepted ⇒ read or handed back: a run that ends without the gate loses nothing to a racing sender."""
    for _ in range(25):
        accepted, read, handed_back = _race_a_teardown_against_senders()
        assert accepted, "the race needs at least one accepted message to mean anything"
        assert sorted(read + handed_back) == sorted(accepted)


def test_redirect_queues_and_sets_flag() -> None:
    t = SteeringToken()
    t.redirect("correction")
    assert t.has_pending is True
    assert t.redirect_requested is True


def test_redirect_requested_false_initially() -> None:
    t = SteeringToken()
    assert t.redirect_requested is False


def test_redirect_reset_by_reset_turn() -> None:
    t = SteeringToken()
    t.redirect("x")
    assert t.redirect_requested is True
    t.reset_turn()
    assert t.redirect_requested is False
    assert t.has_pending is True


def test_redirect_messages_collectible() -> None:
    t = SteeringToken()
    t.redirect("fix this")
    msgs = t.collect_all_steering_messages()
    assert msgs == ["fix this"]


def test_get_set_steering_token() -> None:
    prev = get_steering_token()
    token = SteeringToken()
    set_steering_token(token)
    assert get_steering_token() is token
    set_steering_token(prev)
