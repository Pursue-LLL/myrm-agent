"""Finalize arms the clarification timer of the card the turn stopped at, addressed to that card's pause."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder

CHAT_ID = "chat-clarify-1"
SCHEDULE_CLARIFICATION = "app.services.agent.streaming_support.hitl_timeout.schedule_clarification_timeout"
SCHEDULE_APPROVAL = "app.services.agent.streaming_support.hitl_timeout.schedule_approval_timeout"


def _make_session(card: dict[str, object] | None = None, *, awaiting_answer: bool = False) -> MagicMock:
    session = MagicMock()
    session.request.chat_id = CHAT_ID
    session.request.timezone = "UTC"
    session.request.resume_value = None
    session.collector.has_persistable_turn = False
    session.collector.has_content = False
    session.collector.extra_data = {"clarification": card} if card is not None else {}
    session.collector.has_pending_hitl_replay = MagicMock(return_value=awaiting_answer)
    session.collector.cleanup = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "msg-1"
    return session


@contextmanager
def _finalize_stubs() -> Iterator[None]:
    with (
        patch("app.services.agent.stream_session.stream_finalize.user_credentials_ctx") as mock_ctx,
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
    ):
        mock_ctx.reset = MagicMock()
        yield


async def _finalize(session: MagicMock, approval: ApprovalTimeoutHolder, clarification: ClarificationTimeoutHolder) -> None:
    with _finalize_stubs():
        await finalize_agent_stream_session(session, MagicMock(), approval, clarification)


@pytest.mark.asyncio
async def test_finalize_arms_the_clarification_timer_for_the_card_the_turn_stopped_at() -> None:
    session = _make_session({"answered": False, "interruptId": "int-1"})

    with patch(SCHEDULE_CLARIFICATION) as mock_schedule:
        await _finalize(session, ApprovalTimeoutHolder(), ClarificationTimeoutHolder(pending=True))

    mock_schedule.assert_called_once_with(CHAT_ID, session.params, "int-1")


@pytest.mark.asyncio
async def test_finalize_skips_clarification_timeout_when_not_pending() -> None:
    session = _make_session()

    with patch(SCHEDULE_CLARIFICATION) as mock_schedule:
        await _finalize(session, ApprovalTimeoutHolder(), ClarificationTimeoutHolder(pending=False))

    mock_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_arms_the_clarification_timer_when_only_the_collector_holds_the_card() -> None:
    session = _make_session({"answered": False, "title": "Pick stack", "interruptId": "int-1"})

    with patch(SCHEDULE_CLARIFICATION) as mock_clarify_schedule, patch(SCHEDULE_APPROVAL) as mock_approval_schedule:
        await _finalize(session, ApprovalTimeoutHolder(value={"seconds": 300}), ClarificationTimeoutHolder(pending=False))

    mock_clarify_schedule.assert_called_once_with(CHAT_ID, session.params, "int-1")
    mock_approval_schedule.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "card", [{"answered": False}, {"answered": False, "interruptId": ""}, {"answered": False, "interruptId": 7}]
)
async def test_a_card_without_a_usable_id_gets_no_timer_but_stays_answerable(card: dict[str, object]) -> None:
    """An answer needs the id of its pause to reach it, so a timer without one would only skip into the void."""
    session = _make_session(card, awaiting_answer=True)
    scheduler = MagicMock()

    with patch(SCHEDULE_CLARIFICATION) as mock_schedule, patch.object(ApprovalTimeoutScheduler, "get", return_value=scheduler):
        await _finalize(session, ApprovalTimeoutHolder(), ClarificationTimeoutHolder(pending=True))

    mock_schedule.assert_not_called()
    scheduler.reopen.assert_called_once_with(CHAT_ID)


@pytest.mark.asyncio
async def test_an_answered_card_gets_no_timer() -> None:
    session = _make_session({"answered": True, "interruptId": "int-0"})

    with patch(SCHEDULE_CLARIFICATION) as mock_schedule:
        await _finalize(session, ApprovalTimeoutHolder(), ClarificationTimeoutHolder(pending=False))

    mock_schedule.assert_not_called()
