"""Finalize reopens an interrupt that carries no timer so its manual answer is not refused."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder

CHAT_ID = "chat-reopen-1"


@pytest.fixture(autouse=True)
def _fresh_scheduler() -> Iterator[None]:
    ApprovalTimeoutScheduler._instance = None
    yield
    ApprovalTimeoutScheduler.get().cancel_all()


def _make_session(*, awaiting_answer: bool) -> MagicMock:
    session = MagicMock()
    session.request.chat_id = CHAT_ID
    session.request.timezone = "UTC"
    session.request.resume_value = None
    session.collector.has_persistable_turn = False
    session.collector.has_content = False
    session.collector.extra_data = {}
    session.collector.has_pending_hitl_replay = MagicMock(return_value=awaiting_answer)
    session.collector.cleanup = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "msg-1"
    return session


async def _finalize(session: MagicMock, approval: ApprovalTimeoutHolder | None = None) -> None:
    with (
        patch("app.services.agent.stream_session.stream_finalize.user_credentials_ctx") as mock_ctx,
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(
            session,
            MagicMock(),
            approval or ApprovalTimeoutHolder(),
            ClarificationTimeoutHolder(pending=False),
        )


def _claim_chat_key() -> ApprovalTimeoutScheduler:
    """An earlier interrupt of this chat was already resolved, which leaves its key claimed."""
    scheduler = ApprovalTimeoutScheduler.get()
    assert scheduler.resolve_if_first(CHAT_ID) is True
    return scheduler


@pytest.mark.asyncio
async def test_interrupt_without_timer_is_reopened() -> None:
    scheduler = _claim_chat_key()

    await _finalize(_make_session(awaiting_answer=True))

    assert scheduler.resolve_if_first(CHAT_ID) is True


@pytest.mark.asyncio
async def test_run_without_interrupt_keeps_the_key_resolved() -> None:
    scheduler = _claim_chat_key()

    await _finalize(_make_session(awaiting_answer=False))

    assert scheduler.resolve_if_first(CHAT_ID) is False


@pytest.mark.asyncio
async def test_tool_approval_is_armed_not_merely_reopened() -> None:
    scheduler = _claim_chat_key()

    await _finalize(_make_session(awaiting_answer=True), ApprovalTimeoutHolder(value={"seconds": 600, "behavior": "deny"}))

    assert scheduler.pending_count == 1
