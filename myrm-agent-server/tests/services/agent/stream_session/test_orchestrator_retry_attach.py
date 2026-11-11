"""A retry of the message a chat is running attaches to that turn's stream; any other request on the busy chat is refused.

The gateway session and the stream buffer are the real ones: what the orchestrator decides from them is the contract.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry, ResilientStreamBuffer

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session import run_agent_stream

_STREAMED_BEFORE = "streamed-before-the-retry"
_STREAMED_AFTER = "streamed-after-the-retry"
_STREAMED_EARLIER = "streamed-by-an-earlier-turn"


@dataclass(frozen=True)
class _RunningTurn:
    chat_id: str
    message_id: str
    buffer: ResilientStreamBuffer


def _chunk(text: str) -> str:
    return f'data: {{"type":"message","data":"{text}"}}\n\n'


def _http_request() -> MagicMock:
    http_request = MagicMock()
    # A retry is a new POST: only a reconnect carries Last-Event-ID.
    http_request.headers = {}

    async def _stream():
        yield b""

    http_request.stream = _stream
    return http_request


async def _body(response: StreamingResponse | JSONResponse) -> str:
    """The whole body; a response that attached to a stream nobody ends would wait forever, so it is cut off."""
    assert isinstance(response, StreamingResponse)

    async def _read() -> str:
        parts = [piece if isinstance(piece, str) else bytes(piece).decode() async for piece in response.body_iterator]
        return "".join(parts)

    return await asyncio.wait_for(_read(), timeout=5.0)


@pytest.fixture(autouse=True)
def _pass_the_gates_before_the_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = "app.services.agent.stream_session.orchestrator"
    monkeypatch.setattr(f"{orchestrator}.check_stream_risk", AsyncMock(return_value=None))
    monkeypatch.setattr(f"{orchestrator}.prevalidate_archive_restore_actions", AsyncMock(return_value=None))
    monkeypatch.setattr(f"{orchestrator}._count_pending_approvals", AsyncMock(return_value=0))


@pytest.fixture
async def running_turn() -> AsyncGenerator[_RunningTurn]:
    """A chat with a turn in flight: the gateway holds its session and the turn's buffer has streamed one event."""
    suffix = uuid.uuid4().hex[:8]
    chat_id, message_id = f"chat-attach-{suffix}", f"msg-attach-{suffix}"
    registry = GlobalStreamRegistry.get()
    get_agent_gateway().reserve_session(chat_id, active_message_id=message_id)
    buffer = await registry.start_run(message_id)
    await buffer.append(_chunk(_STREAMED_BEFORE))
    yield _RunningTurn(chat_id, message_id, buffer)
    await registry.remove(message_id)
    get_agent_gateway().release_session(chat_id)


@pytest.mark.asyncio
async def test_retry_of_the_running_message_replays_its_stream_and_follows_it(running_turn: _RunningTurn) -> None:
    request = AgentRequest(message_id=running_turn.message_id, chat_id=running_turn.chat_id, query="hello")

    response = await run_agent_stream(request, _http_request())

    body = asyncio.create_task(_body(response))
    await running_turn.buffer.append(_chunk(_STREAMED_AFTER))
    await running_turn.buffer.end_stream()
    text = await body
    assert _STREAMED_BEFORE in text
    assert _STREAMED_AFTER in text
    assert "AgentBusyError" not in text
    # The retry started nothing of its own: the running turn keeps its session and its buffer.
    assert get_agent_gateway().get_active_message_id(running_turn.chat_id) == running_turn.message_id
    assert await GlobalStreamRegistry.get().get_or_create(running_turn.message_id) is running_turn.buffer


@pytest.mark.asyncio
async def test_retry_of_the_running_message_without_a_stream_buffer_is_busy(running_turn: _RunningTurn) -> None:
    await GlobalStreamRegistry.get().remove(running_turn.message_id)
    request = AgentRequest(message_id=running_turn.message_id, chat_id=running_turn.chat_id, query="hello")

    text = await _body(await run_agent_stream(request, _http_request()))

    assert "AgentBusyError" in text


@pytest.mark.asyncio
async def test_other_message_on_the_busy_chat_is_busy_even_when_it_has_a_finished_stream(running_turn: _RunningTurn) -> None:
    registry = GlobalStreamRegistry.get()
    other_message_id = f"{running_turn.message_id}-other"
    finished = await registry.start_run(other_message_id)
    await finished.append(_chunk(_STREAMED_EARLIER))
    await finished.end_stream()
    request = AgentRequest(message_id=other_message_id, chat_id=running_turn.chat_id, query="hello")

    try:
        text = await _body(await run_agent_stream(request, _http_request()))
    finally:
        await registry.remove(other_message_id)

    assert "AgentBusyError" in text
    assert _STREAMED_EARLIER not in text


@pytest.mark.asyncio
async def test_resume_under_the_running_message_id_is_busy(running_turn: _RunningTurn) -> None:
    request = AgentRequest(
        message_id=running_turn.message_id,
        chat_id=running_turn.chat_id,
        resume_value={"decision": "approve"},
    )

    text = await _body(await run_agent_stream(request, _http_request()))

    assert "AgentBusyError" in text
    assert _STREAMED_BEFORE not in text
