"""API contract: a user retry while agent-stream is still active.

Locks the cross-layer behavior for client retries:
- a retry of the message the chat is running attaches to that turn: it replays the turn's stream and follows it to
  the end, with no second execution and no second user row (a different message on the busy chat is refused as busy,
  which test_reconnect_integration covers)
- a resume that lost the race to the approval timeout is refused with a real HTTP 409
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.stream_buffer import ResilientStreamBuffer

from app.database.dto import MessageDTO
from app.services.agent.execution_cache.prewarm.types import TurnPrewarmJoinResult
from app.services.chat.chat_service import ChatService
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


async def _list_user_messages(chat_id: str) -> list[MessageDTO]:
    messages = await ChatService.get_all_messages(chat_id)
    return [message for message in messages if message.role == "user"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_stream_retry_while_active_attaches_to_the_running_turn(app) -> None:
    """The retry gets the running turn's stream: no busy refusal, no second execution, no second user row."""
    release_first_stream = asyncio.Event()
    retry_attached = asyncio.Event()

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

    mock_coordinator = MagicMock()
    mock_coordinator.join_for_turn = AsyncMock(return_value=_SKIP_PREWARM)

    subscribe = ResilientStreamBuffer.subscribe
    subscriptions = 0

    def _count_subscriptions(buffer: ResilientStreamBuffer, last_event_id: str | None = None) -> AsyncGenerator[str]:
        # The turn's own response subscribes to its buffer once; a second subscription is the retry attaching.
        # The in-process test client hands back a response only after its body is complete, so this is the one
        # signal that the retry reached the running turn.
        nonlocal subscriptions
        if buffer.run_id == message_id:
            subscriptions += 1
            if subscriptions == 2:
                retry_attached.set()
        return subscribe(buffer, last_event_id)

    turns: list[asyncio.Task[list[dict[str, object]]]] = []
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
                return_value=mock_coordinator,
            ),
            patch.object(ResilientStreamBuffer, "subscribe", _count_subscriptions),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                first_turn = asyncio.create_task(_collect_agent_stream_events(client, payload))
                turns.append(first_turn)

                # The turn reserves the chat before it persists the user message, so a retry sent after the
                # persist always meets an active session.
                persist_deadline = asyncio.get_running_loop().time() + 30.0
                while not await _list_user_messages(chat_id):
                    assert not first_turn.done(), f"first agent-stream ended before persisting: {first_turn.result()}"
                    assert asyncio.get_running_loop().time() < persist_deadline, (
                        "first agent-stream never persisted the user message"
                    )
                    await asyncio.sleep(0.05)

                retry_turn = asyncio.create_task(_collect_agent_stream_events(client, payload))
                turns.append(retry_turn)
                try:
                    await asyncio.wait_for(retry_attached.wait(), timeout=30.0)
                except TimeoutError:
                    outcome = retry_turn.result() if retry_turn.done() else "still pending"
                    pytest.fail(f"retry never attached to the running turn: {outcome}")

                release_first_stream.set()
                first_events, retry_events = await asyncio.wait_for(asyncio.gather(first_turn, retry_turn), timeout=30.0)

                assert retry_events == first_events
                assert any(event.get("type") == "message" for event in first_events)
                assert mock_agent.process_stream.call_count == 1
                user_messages = await _list_user_messages(chat_id)
                assert [message.id for message in user_messages] == [message_id]
                assert user_messages[0].content == query_text
    finally:
        release_first_stream.set()
        for turn in turns:
            turn.cancel()
        await asyncio.gather(*turns, return_exceptions=True)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_stream_resume_lost_the_race_is_refused_with_409_over_http(app) -> None:
    """The client acts on the status code, so the refusal must reach it as a real HTTP 409."""
    chat_id = f"chat-resume-race-{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "message_id": f"msg-resume-race-{uuid.uuid4().hex[:8]}",
        "query": "",
        "chat_id": chat_id,
        "model_selection": get_lite_model_selection(),
        "action_mode": "agent",
        "timezone": "UTC",
        "enable_memory": False,
        "resume_value": {"decision": "approve"},
    }
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    scheduler.resolve_if_first(chat_id)  # the approval timer or another client answered first

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post("/api/v1/agents/agent-stream", json=payload, timeout=30.0)

        assert response.status_code == 409
        assert response.json() == {"detail": "This approval has already been resolved."}
    finally:
        scheduler.cancel_all()
