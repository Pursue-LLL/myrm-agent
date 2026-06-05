"""Regression: ``stream_finalize`` CancelledError path must kill background jobs.

uvicorn worker timeouts and abrupt SSE disconnects raise
``asyncio.CancelledError`` *outside* the ``stream_loop`` body, so the
``is_cancelled`` chunk-loop branch never runs. Without this hook,
``npm start`` / dev servers would keep running after the client gives up.
"""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session import stream_finalize
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


def _make_session(chat_id: str | None) -> tuple[AgentStreamSession, MagicMock]:
    cancel_mock = MagicMock()
    session = MagicMock(spec=AgentStreamSession)
    session.request = MagicMock(chat_id=chat_id)
    session.params = MagicMock(message_id="msg-1")
    session.cancel_token = MagicMock()
    session.cancel_token.cancel = cancel_mock
    return cast(AgentStreamSession, session), cancel_mock


@pytest.mark.asyncio
async def test_cancelled_error_kills_session_background_jobs() -> None:
    session, cancel_mock = _make_session(chat_id="chat-xyz")
    fake_registry = MagicMock()
    fake_registry.kill_session_jobs = AsyncMock(return_value=3)

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background_registry.get_background_registry",
        return_value=fake_registry,
    ):
        chunks = [chunk async for chunk in stream_finalize.yield_stream_exception_chunks(session, asyncio.CancelledError())]

    assert chunks == []
    fake_registry.kill_session_jobs.assert_awaited_once_with("chat-xyz")
    cancel_mock.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_error_skips_kill_when_no_chat_id() -> None:
    session, cancel_mock = _make_session(chat_id=None)
    fake_registry = MagicMock()
    fake_registry.kill_session_jobs = AsyncMock()

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background_registry.get_background_registry",
        return_value=fake_registry,
    ):
        async for _ in stream_finalize.yield_stream_exception_chunks(session, asyncio.CancelledError()):
            pass

    fake_registry.kill_session_jobs.assert_not_called()
    cancel_mock.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_error_swallows_kill_failure() -> None:
    session, _ = _make_session(chat_id="chat-fail")
    fake_registry = MagicMock()
    fake_registry.kill_session_jobs = AsyncMock(side_effect=RuntimeError("registry down"))

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background_registry.get_background_registry",
        return_value=fake_registry,
    ):
        async for _ in stream_finalize.yield_stream_exception_chunks(session, asyncio.CancelledError()):  # must NOT raise
            pass

    fake_registry.kill_session_jobs.assert_awaited_once_with("chat-fail")
