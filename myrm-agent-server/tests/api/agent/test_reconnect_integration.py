"""Agent-stream disconnect/reconnect via Last-Event-ID (ASGI integration)."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.agent.execution_cache.prewarm.types import TurnPrewarmJoinResult
from tests.api.agent.utils import get_lite_model_selection


def _parse_sse_chunks(raw: str) -> list[str]:
    chunks: list[str] = []
    for part in raw.split("\n\n"):
        stripped = part.strip()
        if stripped:
            chunks.append(stripped)
    return chunks


def _extract_last_event_id(chunks: list[str]) -> str | None:
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("id:"):
                return line[3:].strip()
    return None


def _skip_prewarm_coordinator():
    """Return a coordinator stub whose join_for_turn always skips.

    The reconnect test mocks AgentFactory.create_general_agent with a
    MagicMock; the real prewarm coordinator would serialize that mock into an
    execution fingerprint and crash, and prewarm itself is not the target of
    this test. Stubbing join_for_turn keeps prewarm out of the turn body.
    """
    stub = MagicMock()
    stub.join_for_turn = AsyncMock(
        return_value=TurnPrewarmJoinResult(
            preview=None,
            snapshot=None,
            brief_status={"state": "skipped", "reason": "test-stub"},
            prewarm_hit=False,
            prewarm_ms=None,
            still_warming=False,
        )
    )
    return stub


async def _collect_stream_text(
    client: httpx.AsyncClient,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
    max_chunks: int | None = None,
) -> tuple[list[str], str]:
    raw = ""
    async with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=payload,
        headers=headers or {},
        timeout=60.0,
    ) as response:
        assert response.status_code == 200
        async for piece in response.aiter_text():
            raw += piece
            if max_chunks is not None:
                parsed = _parse_sse_chunks(raw)
                if len(parsed) >= max_chunks:
                    break
    return _parse_sse_chunks(raw), raw


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_stream_disconnect_and_reconnect(app) -> None:
    """Mid-stream disconnect then Last-Event-ID reconnect replays buffered events."""
    chat_id = f"test-reconnect-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"

    async def _mock_process_stream(*_args: object, **_kwargs: object):
        for index in range(1, 8):
            yield {"type": "message", "data": f"chunk-{index}"}
            await asyncio.sleep(0.05)

    mock_agent = MagicMock()
    mock_agent.process_stream = MagicMock(side_effect=_mock_process_stream)
    mock_agent.release_pooled_session = AsyncMock()
    mock_agent.agent = None

    payload: dict[str, object] = {
        "message_id": message_id,
        "query": "Please count slowly for reconnect testing.",
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
            patch(
                "app.services.agent.execution_cache.prewarm.coordinator.get_turn_prewarm_coordinator",
                return_value=_skip_prewarm_coordinator(),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                first_task = asyncio.create_task(
                    _collect_stream_text(client, payload, max_chunks=3)
                )
                first_chunks, _ = await asyncio.wait_for(first_task, timeout=30.0)
                assert len(first_chunks) >= 3, f"Expected >=3 chunks, got {len(first_chunks)}"

                last_event_id = _extract_last_event_id(first_chunks)
                assert last_event_id, f"No Last-Event-ID in chunks: {first_chunks}"

                await asyncio.sleep(0.2)

                headers = {"Last-Event-ID": last_event_id}
                reconnect_chunks, reconnect_raw = await _collect_stream_text(
                    client,
                    payload,
                    headers=headers,
                )
                assert reconnect_chunks, "Reconnect returned no SSE chunks"
                assert any(
                    "chunk-" in chunk or "message" in chunk for chunk in reconnect_chunks
                ), reconnect_raw

                combined_text = reconnect_raw
                assert any(
                    marker in combined_text
                    for marker in ('"type": "message"', "message_completed", "task_completed")
                ) or "chunk-" in combined_text
    finally:
        pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_stream_early_busy_skips_second_persist(app) -> None:
    """Second turn on active chat is rejected at reserve before creating another user row."""
    from app.services.agent.gateway import get_agent_gateway
    from app.services.chat.chat_service import ChatService

    gateway = get_agent_gateway()
    session_registered = asyncio.Event()
    release_first_stream = asyncio.Event()

    original_sessions = gateway._active_sessions

    class _SessionRegisteredSet(set[str]):
        def __init__(self, event: asyncio.Event) -> None:
            super().__init__()
            self._event = event

        def add(self, item: str) -> None:
            super().add(item)
            self._event.set()

    gateway._active_sessions = _SessionRegisteredSet(session_registered)

    async def _mock_process_stream(*_args: object, **_kwargs: object):
        yield {"type": "message", "data": "early-busy-ok"}
        await release_first_stream.wait()

    mock_agent = MagicMock()
    mock_agent.process_stream = MagicMock(side_effect=_mock_process_stream)
    mock_agent.release_pooled_session = AsyncMock()
    mock_agent.agent = None

    chat_id = f"chat-early-busy-{uuid.uuid4().hex[:8]}"
    first_message_id = f"msg-first-{uuid.uuid4().hex[:8]}"
    second_message_id = f"msg-second-{uuid.uuid4().hex[:8]}"
    first_payload: dict[str, object] = {
        "message_id": first_message_id,
        "query": "First turn for early busy test.",
        "chat_id": chat_id,
        "model_selection": get_lite_model_selection(),
        "action_mode": "agent",
        "timezone": "UTC",
        "enable_memory": False,
    }
    second_payload: dict[str, object] = {
        **first_payload,
        "message_id": second_message_id,
        "query": "Second turn must be rejected early.",
    }

    async def _drain(client: httpx.AsyncClient, payload: dict[str, object]) -> None:
        async with client.stream(
            "POST",
            "/api/v1/agents/agent-stream",
            json=payload,
            timeout=60.0,
        ) as response:
            async for _line in response.aiter_lines():
                pass

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
            patch(
                "app.services.agent.execution_cache.prewarm.coordinator.get_turn_prewarm_coordinator",
                return_value=_skip_prewarm_coordinator(),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                first_task = asyncio.create_task(_drain(client, first_payload))
                await asyncio.wait_for(session_registered.wait(), timeout=30.0)

                persist_deadline = asyncio.get_running_loop().time() + 30.0
                while asyncio.get_running_loop().time() < persist_deadline:
                    messages = await ChatService.get_all_messages(chat_id)
                    if any(message.role == "user" for message in messages):
                        break
                    await asyncio.sleep(0.05)
                else:
                    release_first_stream.set()
                    pytest.fail("First stream never persisted user message")

                busy_resp = await client.post(
                    "/api/v1/agents/agent-stream",
                    json=second_payload,
                )
                assert busy_resp.status_code == 200
                busy_body = await busy_resp.aread()
                busy_text = busy_body.decode(errors="replace")
                assert "AgentBusyError" in busy_text

                messages = await ChatService.get_all_messages(chat_id)
                user_messages = [message for message in messages if message.role == "user"]
                assert len(user_messages) == 1
                assert user_messages[0].id == first_message_id

                release_first_stream.set()
                await asyncio.wait_for(first_task, timeout=30.0)
    finally:
        release_first_stream.set()
        gateway._active_sessions = original_sessions
        if "first_task" in locals() and not first_task.done():
            first_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_task
