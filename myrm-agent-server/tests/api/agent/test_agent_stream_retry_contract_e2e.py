"""API contract: idempotent user retry while agent-stream is still active.

Locks the cross-layer behavior for client retries:
- same chat_id + message_id + content must not create a second user turn
- a retry while the chat session is still active must surface AgentBusyError (409 SSE)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.database.dto import MessageDTO
from app.services.chat.chat_service import ChatService
from tests.api.agent.utils import get_lite_model_selection


class _SessionRegisteredSet(set[str]):
    """Fire an asyncio.Event when a chat_id is registered as active."""

    def __init__(self, event: asyncio.Event) -> None:
        super().__init__()
        self._event = event

    def add(self, item: str) -> None:
        super().add(item)
        self._event.set()


async def _collect_agent_stream_events(
    client: httpx.AsyncClient,
    payload: dict[str, object],
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    async with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=payload,
        timeout=60.0,
    ) as response:
        if response.status_code != 200:
            raw = await response.aread()
            return [
                {
                    "type": "http_error",
                    "status": response.status_code,
                    "text": raw.decode(errors="replace"),
                }
            ]
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                parsed = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return events


async def _list_user_messages(chat_id: str) -> list[MessageDTO]:
    messages = await ChatService.get_all_messages(chat_id)
    return [message for message in messages if message.role == "user"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_stream_retry_while_active_is_idempotent_and_busy(app) -> None:
    """Same message_id retry during an active turn must not duplicate the user row."""
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    session_registered = asyncio.Event()
    release_first_stream = asyncio.Event()

    original_sessions = gateway._active_sessions
    gateway._active_sessions = _SessionRegisteredSet(session_registered)

    async def _mock_process_stream(*_args: object, **_kwargs: object):
        yield {"type": "message", "data": "retry-contract-ok"}
        await release_first_stream.wait()

    mock_agent = MagicMock()
    mock_agent.process_stream = MagicMock(side_effect=_mock_process_stream)
    mock_agent.release_pooled_session = AsyncMock()
    mock_agent.agent = None

    chat_id = f"chat-retry-contract-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-retry-contract-{uuid.uuid4().hex[:8]}"
    query_text = "Please keep this turn stable for retry contract testing."
    payload: dict[str, object] = {
        "message_id": message_id,
        "query": query_text,
        "chat_id": chat_id,
        "model_selection": get_lite_model_selection(),
        "action_mode": "agent",
        "timezone": "UTC",
        "enable_memory": False,
    }

    try:
        with (
            patch(
                "app.services.agent.streaming.AgentFactory.create_general_agent",
                return_value=mock_agent,
            ),
            patch(
                "app.services.agent.streaming.convert_chat_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.chat.conversation_recall_index_service.ConversationRecallIndexService.append_message",
                new=AsyncMock(),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                first_task = asyncio.create_task(
                    _collect_agent_stream_events(client, payload)
                )

                try:
                    await asyncio.wait_for(session_registered.wait(), timeout=30.0)
                except TimeoutError:
                    if not first_task.done():
                        first_task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first_task
                    pytest.fail(
                        "First agent-stream never registered an active chat session"
                    )

                retry_events = await _collect_agent_stream_events(client, payload)

                user_messages = await _list_user_messages(chat_id)
                assert (
                    len(user_messages) == 1
                ), f"expected one persisted user turn, found {len(user_messages)} for chat_id={chat_id}"
                assert user_messages[0].id == message_id
                assert user_messages[0].content == query_text

                assert retry_events, "Retry request should emit at least one SSE event"
                retry_error = next(
                    (event for event in retry_events if event.get("type") == "error"),
                    None,
                )
                assert (
                    retry_error is not None
                ), f"Expected busy error event, got: {retry_events}"
                assert retry_error.get("error_type") == "AgentBusyError"
                assert retry_error.get("status_code") == 409
                assert retry_error.get("data") == (
                    "Agent is busy processing another request for this session."
                )

                release_first_stream.set()
                first_events = await asyncio.wait_for(first_task, timeout=30.0)
                assert any(event.get("type") == "message" for event in first_events)
    finally:
        release_first_stream.set()
        gateway._active_sessions = original_sessions
        if "first_task" in locals() and not first_task.done():
            first_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_task
