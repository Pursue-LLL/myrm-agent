"""A clarify skip counts as successful only when the agent continued afterwards.

Real scenario: a skip that named no pause reached nobody. The run ended in a bare `message_end` (or announced the
card again) and the E2E that sent it took the stream ending for success. These tests pin the evidence a skip is
judged by, and the address it is sent with.
"""

from __future__ import annotations

import pytest
from cdp_chat.clarify_skip import (
    continued_after_skip,
    open_clarification,
    pending_clarification_interrupt_id,
    skip_resume_value,
    sse_message_text,
)
from myrm_agent_harness.agent.streaming.interrupt_events import INTERRUPT_ID_KEY

Event = dict[str, object]


def _text(chunk: str) -> Event:
    return {"type": "message", "data": chunk}


def _kind(kind: str) -> Event:
    return {"type": kind}


def _card(*, answered: bool, interrupt_id: str | None = "int-1", container: str = "metadata") -> Event:
    card: dict[str, object] = {"answered": answered}
    if interrupt_id is not None:
        card[INTERRUPT_ID_KEY] = interrupt_id
    return {"role": "assistant", "content": "", container: {"clarification": card}}


class TestContinuedAfterSkip:
    def test_text_after_the_skip_is_continuation(self) -> None:
        events = [_kind("progress"), _text("DONE-"), _text("SKIPPED"), _kind("message_end")]

        assert sse_message_text(events) == "DONE-SKIPPED"
        assert continued_after_skip(events) is True

    @pytest.mark.parametrize(
        "events",
        [
            pytest.param([_kind("progress"), _kind("message_end")], id="bare-message-end"),
            pytest.param(
                [_kind("progress"), _kind("clarification_required"), _kind("message_end")],
                id="card-announced-again",
            ),
            pytest.param([_text("Let me ask first"), _kind("clarification_required")], id="text-then-card-again"),
            pytest.param([_kind("error"), _text("partial")], id="error"),
            pytest.param([_text("  \n"), _kind("message_end")], id="blank-text"),
            pytest.param([], id="no-events"),
        ],
    )
    def test_a_stream_that_merely_ends_is_not_continuation(self, events: list[Event]) -> None:
        assert continued_after_skip(events) is False


class TestSkipAddress:
    def test_skip_names_the_pause_it_answers(self) -> None:
        assert skip_resume_value("int-9") == {INTERRUPT_ID_KEY: "int-9"}


class TestStoredCard:
    def test_the_newest_unanswered_card_is_open_and_names_its_pause(self) -> None:
        messages = [{"role": "user", "content": "ask"}, _card(answered=False, interrupt_id="int-2")]

        assert open_clarification(messages) == {"answered": False, INTERRUPT_ID_KEY: "int-2"}
        assert pending_clarification_interrupt_id(messages) == "int-2"

    def test_the_card_may_be_stored_under_either_container(self) -> None:
        messages = [_card(answered=False, interrupt_id="int-3", container="extra_data")]

        assert pending_clarification_interrupt_id(messages) == "int-3"

    def test_an_answered_newest_card_hides_an_older_open_one(self) -> None:
        messages = [_card(answered=False, interrupt_id="int-old"), _card(answered=True, interrupt_id="int-new")]

        assert open_clarification(messages) is None
        assert pending_clarification_interrupt_id(messages) is None

    def test_text_after_the_card_does_not_close_it(self) -> None:
        messages = [_card(answered=False), {"role": "assistant", "content": "still thinking"}, "not a message"]

        assert pending_clarification_interrupt_id(messages) == "int-1"

    def test_a_card_stored_without_an_id_is_open_but_unaddressable(self) -> None:
        messages = [_card(answered=False, interrupt_id=None)]

        assert open_clarification(messages) is not None
        assert pending_clarification_interrupt_id(messages) is None

    def test_a_chat_without_cards_has_nothing_open(self) -> None:
        assert open_clarification([{"role": "user", "content": "hi"}]) is None
        assert pending_clarification_interrupt_id([]) is None
