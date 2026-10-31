"""Stand-ins around ``hitl_timeout._resume_after_timeout`` shared by the unit tests of the run a fired approval timer starts.

[INPUT]
- app.services.agent.streaming_support.stream_collector (POS: the parked run's collector)
- app.services.copilot.run_digest_store (POS: the run digest the timer run must end)

[OUTPUT]
- CHAT_ID / params_of_the_card(): the chat and the run params the timer was armed with
- card_collector(): the parked run, a collector that holds an unanswered tool-approval card
- digest_phase(): the phase of the chat's run digest (None when there is none)
- granted_lease() / stopped_lease() / refused_lease() / interrupted_lease(): the session lease the timer run asks for, as it is granted, granted to a run the user stops, refused, or never reached

[POS]
Used by tests/services/agent/streaming_support/hitl_timeout_resume/ (its conftest.py holds the fixtures built on these).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.gateway import AgentBusyError
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.copilot.run_digest_store import RunDigestStore

CHAT_ID = "chat-timer-card"


def card_collector(chat_id: str) -> StreamContentCollector:
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event({"type": "tool_approval_request", "messageId": "msg-1", "data": {"actionRequests": []}})
    assert collector.has_pending_tool_approval() is True
    return collector


def digest_phase() -> RunDigestPhase | None:
    digest = RunDigestStore.get(CHAT_ID)
    return digest.phase if digest else None


def params_of_the_card() -> MagicMock:
    params = MagicMock()
    params.chat_id = CHAT_ID
    params.message_id = "msg-1"
    params.agent_id = "agent-timer"
    params.timezone = "Asia/Shanghai"
    params.model_copy.return_value = params
    return params


def _token(*, cancelled: bool) -> MagicMock:
    token = MagicMock()
    token.is_cancelled = cancelled
    token.cancel_reason = "user_cancelled" if cancelled else None
    return token


@asynccontextmanager
async def granted_lease(_chat_id: str, _turn_id: str) -> AsyncIterator[MagicMock]:
    yield _token(cancelled=False)


@asynccontextmanager
async def stopped_lease(_chat_id: str, _turn_id: str) -> AsyncIterator[MagicMock]:
    """The user pressed Stop: the run ends quietly with its cancel token set."""
    yield _token(cancelled=True)


@asynccontextmanager
async def refused_lease(_chat_id: str, _turn_id: str) -> AsyncIterator[MagicMock]:
    raise AgentBusyError("a live run holds the chat")
    yield MagicMock()  # pragma: no cover - makes this a generator


@asynccontextmanager
async def interrupted_lease(_chat_id: str, _turn_id: str) -> AsyncIterator[MagicMock]:
    """The task is cancelled before it holds the chat: it never started a run."""
    raise asyncio.CancelledError
    yield MagicMock()  # pragma: no cover - makes this a generator
