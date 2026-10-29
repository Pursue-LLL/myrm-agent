"""A Last-Event-ID reconnect lands on the run that currently owns the message id, including a run that resumed an approval."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from fastapi.responses import StreamingResponse
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

from app.services.agent.stream_session.reconnect import try_stream_reconnect


def _chunk(text: str) -> str:
    return f'data: {{"type":"message","data":"{text}"}}\n\n'


def _event_id(payload: str) -> str:
    return payload.split("\n")[0].removeprefix("id: ")


def _request(message_id: str) -> MagicMock:
    request = MagicMock()
    request.message_id = message_id
    return request


def _http_request(last_event_id: str | None) -> MagicMock:
    http_request = MagicMock()
    http_request.headers = {"Last-Event-ID": last_event_id} if last_event_id else {}
    return http_request


async def _let_the_clock_tick() -> None:
    """Event ids are `<ms>-<seq>`; a human approval never resumes within the asking event's millisecond, so the test must not either."""
    await asyncio.sleep(0.01)


async def _body(response: StreamingResponse) -> str:
    parts: list[str] = []
    async for piece in response.body_iterator:
        parts.append(piece if isinstance(piece, str) else bytes(piece).decode())
    return "".join(parts)


@pytest.fixture
async def message_id() -> AsyncGenerator[str]:
    run_id = f"msg-reconnect-{uuid.uuid4().hex[:8]}"
    yield run_id
    await GlobalStreamRegistry.get().remove(run_id)


@pytest.mark.asyncio
async def test_reconnect_with_the_asking_turns_event_id_replays_the_resumed_turn(message_id: str) -> None:
    registry = GlobalStreamRegistry.get()
    asking = await registry.get_or_create(message_id)
    stopped_id = _event_id(await asking.append(_chunk("asked-for-approval")))
    await asking.end_stream()
    await _let_the_clock_tick()
    resumed = await registry.start_run(message_id)
    await resumed.append(_chunk("resumed-reply"))
    await resumed.end_stream()

    response = await try_stream_reconnect(_request(message_id), _http_request(stopped_id))

    assert isinstance(response, StreamingResponse)
    body = await _body(response)
    assert "resumed-reply" in body
    assert "asked-for-approval" not in body


@pytest.mark.asyncio
async def test_reconnect_inside_the_resumed_turn_continues_after_the_event_it_saw(message_id: str) -> None:
    registry = GlobalStreamRegistry.get()
    await (await registry.get_or_create(message_id)).end_stream()
    await _let_the_clock_tick()
    resumed = await registry.start_run(message_id)
    seen_id = _event_id(await resumed.append(_chunk("seen-before-the-drop")))
    await resumed.append(_chunk("missed-during-the-drop"))
    await resumed.end_stream()

    response = await try_stream_reconnect(_request(message_id), _http_request(seen_id))

    assert isinstance(response, StreamingResponse)
    body = await _body(response)
    assert "missed-during-the-drop" in body
    assert "seen-before-the-drop" not in body


@pytest.mark.asyncio
async def test_reconnect_after_the_buffer_is_gone_says_the_session_expired(message_id: str) -> None:
    response = await try_stream_reconnect(_request(message_id), _http_request("1-1"))

    assert isinstance(response, StreamingResponse)
    assert "Session expired" in await _body(response)


@pytest.mark.asyncio
async def test_a_request_without_last_event_id_is_not_a_reconnect(message_id: str) -> None:
    assert await try_stream_reconnect(_request(message_id), _http_request(None)) is None
