"""The record a settled clarification card keeps holds the answer the user gave, not the address it was sent to."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.answered_cards import settle_answered_cards


def _session(resume_value: dict[str, object] | None, chat_id: str | None = "chat-1") -> MagicMock:
    session = MagicMock()
    session.request.chat_id = chat_id
    session.request.resume_value = resume_value
    return session


async def _settle(session: MagicMock) -> AsyncMock:
    with patch(
        "app.services.agent.stream_session.answered_cards.mark_pending_clarification_answered",
        new_callable=AsyncMock,
    ) as mark:
        await settle_answered_cards(session)
    return mark


@pytest.mark.asyncio
async def test_the_record_keeps_the_answer_without_the_id_it_was_addressed_to() -> None:
    mark = await _settle(_session({"strategy": "canary", "interruptId": "int-1"}))

    mark.assert_awaited_once_with("chat-1", {"by": "user", "value": {"strategy": "canary"}})


@pytest.mark.asyncio
async def test_a_skip_leaves_an_empty_record_value_so_the_card_reads_as_skipped() -> None:
    mark = await _settle(_session({"interruptId": "int-1"}))

    mark.assert_awaited_once_with("chat-1", {"by": "user", "value": {}})


@pytest.mark.asyncio
async def test_an_answer_that_was_not_addressed_is_recorded_as_given() -> None:
    mark = await _settle(_session({"strategy": "canary"}))

    mark.assert_awaited_once_with("chat-1", {"by": "user", "value": {"strategy": "canary"}})


@pytest.mark.asyncio
async def test_a_resume_value_without_an_id_is_never_altered() -> None:
    decisions: dict[str, object] = {"decisions": [{"type": "approve"}]}

    mark = await _settle(_session(decisions))

    mark.assert_awaited_once_with("chat-1", {"by": "user", "value": {"decisions": [{"type": "approve"}]}})
    assert decisions == {"decisions": [{"type": "approve"}]}


@pytest.mark.asyncio
async def test_the_answer_the_run_resumed_with_keeps_its_id() -> None:
    """The record is a copy: the resume value the run already consumed must not lose the id it carried."""
    resume_value: dict[str, object] = {"strategy": "canary", "interruptId": "int-1"}

    await _settle(_session(resume_value))

    assert resume_value == {"strategy": "canary", "interruptId": "int-1"}
