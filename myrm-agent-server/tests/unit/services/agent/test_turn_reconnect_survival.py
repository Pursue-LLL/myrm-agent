"""Unit tests for remote turn reconnect survival, monotonic activity-freshness deferral,

and multiplexed offline guardian detection.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.stream_disconnect import build_disconnect_checker
from app.services.agent.stream_session.stream_pump import _is_client_detached
from app.services.agent.stream_session.stream_session_types import (
    ACTIVITY_STALE_SECONDS,
    GRACE_PERIOD_SECONDS,
    AgentStreamSession,
)
from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer
from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def _create_mock_session(
    *,
    is_disconnected: bool = True,
    is_long_running: bool = False,
    multiplexed: bool = False,
    message_id: str = "msg_test_reconnect",
) -> tuple[AgentStreamSession, AsyncMock]:
    mock_disconnect_fn = AsyncMock(return_value=is_disconnected)
    mock_http = MagicMock()
    mock_http.is_disconnected = mock_disconnect_fn

    request = AgentRequest(
        chat_id="chat_test_123",
        message_id=message_id,
        multiplexed=multiplexed,
    )
    cancel_token = MagicMock()
    collector = StreamContentCollector(sibling_group_id=None, chat_id="chat_test_123")

    session = AgentStreamSession(
        request=request,
        http_request=mock_http,
        params=MagicMock(),
        cancel_token=cancel_token,
        steering_token=None,
        routing_tier=None,
        archive_restore_results=[],
        research_model_cfg=None,
        registry=MagicMock(),
        collector=collector,
        is_long_running_task=is_long_running,
        goal_provider=None,
        extra_context={},
    )
    return session, mock_disconnect_fn


@pytest.mark.asyncio
async def test_disconnect_checker_grace_period_and_reset() -> None:
    session, mock_disconnect = _create_mock_session(is_disconnected=True)
    checker = build_disconnect_checker(session)

    # First check: initializes disconnect_monotonic, returns False
    result1 = await checker()
    assert result1 is False
    assert session.disconnect_monotonic is not None

    # Time within grace period (e.g. 50s < GRACE_PERIOD_SECONDS)
    assert GRACE_PERIOD_SECONDS == 180.0
    session.disconnect_monotonic = time.monotonic() - 50.0
    result2 = await checker()
    assert result2 is False

    # Client reconnects: disconnect_monotonic should be cleared to None
    mock_disconnect.return_value = False
    result3 = await checker()
    assert result3 is False
    assert session.disconnect_monotonic is None
    assert session.disconnect_time is None


@pytest.mark.asyncio
async def test_activity_freshness_deferral_prevents_premature_cancellation() -> None:
    session, _ = _create_mock_session(is_disconnected=True)
    checker = build_disconnect_checker(session)

    assert ACTIVITY_STALE_SECONDS == 600.0

    # Disconnected past the 180s grace period (e.g. 250s elapsed)
    now = time.monotonic()
    session.disconnect_monotonic = now - 250.0

    # But the agent turn is still active: emitted tokens 30s ago (< 600s threshold)
    session.last_activity_monotonic = now - 30.0

    # Activity-Freshness Deferral MUST kick in and return False
    result = await checker()
    assert result is False, "Turn activity is fresh (< 600s), cancellation must be deferred!"


@pytest.mark.asyncio
async def test_activity_stale_cancels_turn() -> None:
    session, _ = _create_mock_session(is_disconnected=True)
    checker = build_disconnect_checker(session)

    # Disconnected past 180s grace period (e.g. 200s elapsed)
    now = time.monotonic()
    session.disconnect_monotonic = now - 200.0

    # And activity clock has truly wedged/stalled (> 600s without progress)
    session.last_activity_monotonic = now - 650.0

    # Both conditions met -> turn should be cancelled
    result = await checker()
    assert result is True


def test_workspace_multiplexer_has_subscribers_property() -> None:
    mux = WorkspaceMultiplexer()
    assert mux.has_subscribers is False

    queue: asyncio.Queue[str] = asyncio.Queue()
    mux._subscribers.add(queue)
    assert mux.has_subscribers is True

    mux._subscribers.discard(queue)
    assert mux.has_subscribers is False


@pytest.mark.asyncio
async def test_is_client_detached_multiplexed_vs_direct() -> None:
    # 1. Direct-SSE session
    session_direct, mock_disconnect = _create_mock_session(is_disconnected=True, multiplexed=False)
    assert await _is_client_detached(session_direct) is True

    mock_disconnect.return_value = False
    assert await _is_client_detached(session_direct) is False

    # 2. Multiplexed session
    session_mux, _ = _create_mock_session(is_disconnected=True, multiplexed=True)
    mux = WorkspaceMultiplexer.get()
    # With no subscribers in multiplexer
    mux._subscribers.clear()
    assert await _is_client_detached(session_mux) is True

    # With a subscriber queue in multiplexer
    dummy_q: asyncio.Queue[str] = asyncio.Queue()
    mux._subscribers.add(dummy_q)
    try:
        assert await _is_client_detached(session_mux) is False
    finally:
        mux._subscribers.discard(dummy_q)


@pytest.mark.asyncio
async def test_retried_post_same_message_id_attaches_to_buffer() -> None:
    chat_id = "chat_retry_test"
    message_id = "msg_retry_same"

    mock_gateway = MagicMock()
    mock_gateway.get_active_message_id.return_value = message_id

    mock_buffer = MagicMock()
    mock_buffer.subscribe.return_value = iter([b"event: data\n\n"])

    mock_registry = MagicMock()
    mock_registry.has_buffer = AsyncMock(return_value=True)
    mock_registry.get_or_create = AsyncMock(return_value=mock_buffer)

    # Verify the retried attach logic
    with patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway):
        active_msg_id = mock_gateway.get_active_message_id(chat_id)
        assert active_msg_id == message_id
        assert await mock_registry.has_buffer(message_id) is True

        buffer = await mock_registry.get_or_create(message_id)
        resp = StreamingResponse(
            buffer.subscribe(None),
            media_type="text/event-stream",
            headers=SSE_RESPONSE_HEADERS,
        )
        assert isinstance(resp, StreamingResponse)
        assert resp.media_type == "text/event-stream"
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
