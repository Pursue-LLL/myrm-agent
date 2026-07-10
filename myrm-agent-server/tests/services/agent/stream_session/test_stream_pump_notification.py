"""Tests for stream_pump.py Offline Guardian notification logic.

Validates that:
1. Successful offline long-running tasks produce type="success" notifications
2. Failed offline long-running tasks produce type="error" notifications
3. Online tasks (user connected) do NOT produce notifications
4. Cancelled tasks do NOT produce notifications
5. SSE error chunks are detected and produce error notifications
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_pump import pump_to_buffer

_PUMP_STREAM_PATH = "app.services.agent.stream_session.stream_pump.generate_cancellable_stream"
_MUX_PATH = "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer"
_NOTIF_PATH = "app.services.infra.system_notification.SystemNotificationService.create_notification"


def _make_session(
    *,
    is_long_running: bool = True,
    is_cancelled: bool = False,
    is_disconnected: bool = True,
    durable_registered: bool = False,
    chat_id: str = "test-chat-123",
    message_id: str = "test-msg-456",
) -> MagicMock:
    session = MagicMock()
    session.is_long_running_task = is_long_running
    session.cancel_token.is_cancelled = is_cancelled
    session.durable_registered = durable_registered
    session.had_fatal_error = False
    session.request.chat_id = chat_id
    session.params.message_id = message_id
    session.params.project_id = None
    session.collector = MagicMock()
    session.http_request.is_disconnected = AsyncMock(return_value=is_disconnected)
    session.registry.remove = AsyncMock()
    return session


def _make_buffer() -> MagicMock:
    buf = MagicMock()
    buf.append = AsyncMock()
    buf.end_stream = AsyncMock()
    buf.subscribe = MagicMock(return_value=iter([]))
    return buf


async def _run_pump(session: MagicMock, buf: MagicMock, gen):
    """Helper to run pump_to_buffer with patched dependencies."""
    with (
        patch(_PUMP_STREAM_PATH, return_value=gen),
        patch(_MUX_PATH) as mock_mux,
        patch(_NOTIF_PATH, new_callable=AsyncMock) as mock_notif,
    ):
        mock_mux.get.return_value.publish = AsyncMock()
        await pump_to_buffer(session, buf)
    return mock_notif


@pytest.mark.asyncio
async def test_offline_success_notification():
    """Offline long-running task completes successfully → type=success notification."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "hello"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args[1]
    assert call_kwargs["type"] == "success"
    assert call_kwargs["title"] == "Task Completed"
    assert call_kwargs["source"] == "offline_guardian"
    assert call_kwargs["meta_data"]["action_url"] == "/test-chat-123"


@pytest.mark.asyncio
async def test_offline_error_from_exception_notification():
    """Offline long-running task raises exception → type=error notification."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "partial"}\n\n'
        raise RuntimeError("LLM 529 exhausted")

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args[1]
    assert call_kwargs["type"] == "error"
    assert call_kwargs["title"] == "Task Failed"


@pytest.mark.asyncio
async def test_offline_error_from_sse_error_chunk():
    """Offline task yields SSE error chunk (harness-layer error) → type=error notification."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "partial work"}\n\n'
        yield 'data: {"type": "error", "data": "LLM overloaded", "messageId": "test"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    call_kwargs = mock_notif.call_args[1]
    assert call_kwargs["type"] == "error"
    assert call_kwargs["title"] == "Task Failed"


@pytest.mark.asyncio
async def test_online_task_no_notification():
    """Online task (user connected) → no notification created."""
    session = _make_session(is_disconnected=False)
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "hello"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())
    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_task_no_notification():
    """Cancelled task → no notification created."""
    session = _make_session(is_cancelled=True)
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "hello"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())
    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_short_task_no_notification():
    """Non-long-running task → no notification created."""
    session = _make_session(is_long_running=False)
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "hello"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())
    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_error_notification_message_is_user_friendly():
    """Error notification message should NOT leak technical details."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "error", "data": "HTTP 429 rate_limit_exceeded"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    call_kwargs = mock_notif.call_args[1]
    assert "429" not in call_kwargs["message"]
    assert "rate_limit" not in call_kwargs["message"]
    assert "check the chat" in call_kwargs["message"].lower()


@pytest.mark.asyncio
async def test_meta_data_contains_chat_and_message_id():
    """Notification meta_data must contain chat_id and message_id for frontend routing."""
    session = _make_session(chat_id="chat-abc", message_id="msg-xyz")
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "done"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    meta = mock_notif.call_args[1]["meta_data"]
    assert meta["chat_id"] == "chat-abc"
    assert meta["message_id"] == "msg-xyz"
    assert meta["action_url"] == "/chat-abc"


@pytest.mark.asyncio
async def test_multiple_error_chunks_only_one_notification():
    """Multiple SSE error chunks should still produce only ONE notification."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "error", "data": "first error"}\n\n'
        yield 'data: {"type": "error", "data": "second error"}\n\n'
        yield 'data: {"type": "error", "data": "third error"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    assert mock_notif.call_args[1]["type"] == "error"


@pytest.mark.asyncio
async def test_empty_stream_success_notification():
    """Empty stream (0 chunks) still counts as successful if no errors."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        return
        yield  # make it an async generator

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    assert mock_notif.call_args[1]["type"] == "success"


@pytest.mark.asyncio
async def test_had_fatal_error_session_flag_produces_error_notification():
    """session.had_fatal_error=True → error notification regardless of stream content."""
    session = _make_session()
    session.had_fatal_error = True
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "looks ok"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    assert mock_notif.call_args[1]["type"] == "error"


@pytest.mark.asyncio
async def test_cancelled_error_with_token_suppresses_notification():
    """asyncio.CancelledError + cancel_token.is_cancelled=True → no notification."""
    import asyncio as _asyncio

    session = _make_session(is_cancelled=True)
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "partial"}\n\n'
        raise _asyncio.CancelledError()

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_error_without_token_sends_success():
    """asyncio.CancelledError but cancel_token NOT set → success notification (external timeout)."""
    import asyncio as _asyncio

    session = _make_session(is_cancelled=False)
    buf = _make_buffer()

    async def _gen():
        yield 'data: {"type": "message", "data": "partial"}\n\n'
        raise _asyncio.CancelledError()

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    assert mock_notif.call_args[1]["type"] == "success"


@pytest.mark.asyncio
async def test_whitespace_only_chunks_ignored():
    """Chunks that are whitespace-only should not be processed for error detection."""
    session = _make_session()
    buf = _make_buffer()

    async def _gen():
        yield '   \n\n'
        yield '\n'
        yield 'data: {"type": "message", "data": "real content"}\n\n'

    mock_notif = await _run_pump(session, buf, _gen())

    mock_notif.assert_called_once()
    assert mock_notif.call_args[1]["type"] == "success"
