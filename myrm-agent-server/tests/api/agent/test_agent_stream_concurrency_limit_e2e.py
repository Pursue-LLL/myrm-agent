"""Integration: concurrency-limit queue timeout renders a structured SSE error.

Real full path — agent-stream API -> gateway.execute_stream (throws
AgentQueueTimeout) -> stream_chunks BaseException fallback ->
yield_stream_exception_chunks -> SSE with error_kind=concurrency_limit.

A suspended direct gateway execution occupies the only concurrency slot; the
second turn arrives over the real HTTP agent-stream endpoint and must surface
the structured concurrency_limit error instead of hanging.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.agent.execution_cache.prewarm.types import TurnPrewarmJoinResult
from app.services.agent.gateway import GatewayConfig, get_agent_gateway
from tests.api.agent.utils import get_lite_model_selection

_SKIP_PREWARM = TurnPrewarmJoinResult(
    preview=None,
    snapshot=None,
    brief_status={"state": "skipped", "reason": "test"},
    prewarm_hit=False,
    prewarm_ms=None,
    still_warming=False,
)


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


async def _drain(
    stream: AsyncGenerator[dict[str, object], None],
) -> list[dict[str, object]]:
    return [event async for event in stream]


def _stream_payload(chat_id: str, message_id: str) -> dict[str, object]:
    return {
        "message_id": message_id,
        "query": "Please return the concurrency limit structured error contract.",
        "chat_id": chat_id,
        "model_selection": get_lite_model_selection(),
        "action_mode": "agent",
        "timezone": "UTC",
        "enable_memory": False,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_stream_queue_timeout_renders_structured_concurrency_error(
    app,
) -> None:
    """Queue timeout during a real agent-stream emits error_kind=concurrency_limit."""
    gateway = get_agent_gateway()
    original_config = gateway._config
    original_global_sem = gateway._global_sem
    original_sessions = gateway._active_sessions

    gateway._config = GatewayConfig(
        max_global=1,
        max_per_user=1,
        queue_timeout=0.4,
        execution_timeout=30.0,
    )
    gateway._global_sem = asyncio.Semaphore(1)

    holder_release = asyncio.Event()
    holder_chat = f"chat-concurrency-holder-{uuid.uuid4().hex[:8]}"

    async def _suspended_holder_stream() -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "concurrency-limit-holder-ok"}
        await holder_release.wait()

    holder_task: asyncio.Task[list[dict[str, object]]] | None = None

    waiter_chat = f"chat-concurrency-waiter-{uuid.uuid4().hex[:8]}"
    waiter_message = f"msg-concurrency-waiter-{uuid.uuid4().hex[:8]}"

    mock_coordinator = MagicMock()
    mock_coordinator.join_for_turn = AsyncMock(return_value=_SKIP_PREWARM)

    try:
        holder_task = asyncio.create_task(
            _drain(
                gateway.execute_stream(
                    _suspended_holder_stream(),
                    agent_type="general",
                    session_id=holder_chat,
                )
            )
        )
        try:
            await asyncio.wait_for(_wait_until_active(gateway, holder_chat), timeout=10.0)
        except TimeoutError:
            pytest.fail("Holder execution never occupied the gateway slot")

        with (
            patch(
                "app.services.agent.streaming.AgentFactory.create_general_agent",
                return_value=MagicMock(
                    process_stream=MagicMock(
                        side_effect=AsyncMock(return_value=iter([]))
                    ),
                    release_pooled_session=AsyncMock(),
                    agent=None,
                ),
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
                return_value=mock_coordinator,
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                waiter_events = await _collect_agent_stream_events(
                    client,
                    _stream_payload(waiter_chat, waiter_message),
                )

                assert waiter_events, "Waiter request should emit at least one SSE event"
                error_event = next(
                    (event for event in waiter_events if event.get("type") == "error"),
                    None,
                )
                assert error_event is not None, (
                    f"Expected concurrency error event, got: {waiter_events}"
                )
                assert error_event.get("error_kind") == "concurrency_limit"
                assert error_event.get("messageId") == waiter_message
                diagnostic = error_event.get("diagnostic_result")
                assert isinstance(diagnostic, dict)
                assert diagnostic["error_type"] == "concurrency_limit"
                assert "Server is busy" in str(diagnostic["user_message"])
                assert isinstance(diagnostic["resolution_steps"], list)
                assert holder_chat in str(diagnostic["user_message"])

                holder_release.set()
                holder_events = await asyncio.wait_for(holder_task, timeout=10.0)
                assert any(
                    event.get("type") == "message" for event in holder_events
                ), "Holder stream should still complete after slot release"
    finally:
        holder_release.set()
        gateway._active_sessions = original_sessions
        gateway._config = original_config
        gateway._global_sem = original_global_sem
        if holder_task is not None and not holder_task.done():
            holder_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await holder_task


async def _wait_until_active(gateway, chat_id: str) -> None:
    for _ in range(200):
        if gateway.is_session_active(chat_id):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"chat_id={chat_id} never became active")
