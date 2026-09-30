"""Unit tests for SessionTurnArbiter priority enforcement."""

import time

from app.services.loop.session_turn_arbiter import SessionTurnArbiter


def test_turn_arbiter_records_activity_and_defers() -> None:
    arbiter = SessionTurnArbiter()
    chat_id = "test-chat-123"

    assert not arbiter.should_defer_loop_wakeup(chat_id)

    arbiter.record_user_activity(chat_id)
    assert arbiter.should_defer_loop_wakeup(chat_id, grace_period_seconds=1.0)

    time.sleep(1.05)
    assert not arbiter.should_defer_loop_wakeup(chat_id, grace_period_seconds=1.0)

    arbiter.clean_chat(chat_id)
    assert not arbiter.should_defer_loop_wakeup(chat_id)
