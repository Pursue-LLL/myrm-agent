"""The agent test clients (sync ``TestClient`` and async ``httpx.AsyncClient``) hide SSE keep-alive frames
from line-oriented parsers.

The frames are produced by the real ``ResilientStreamBuffer``, so a change to the heartbeat wire
format fails here instead of silently re-opening the ``data: null`` parsing hole in the stream
tests that do ``json.loads(line[6:]).get("type")``.
"""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.streaming.stream_buffer import ResilientStreamBuffer

from tests.api.agent.utils import adrop_sse_heartbeats, drop_sse_heartbeats, hide_sse_heartbeats, hide_sse_heartbeats_async

_HEARTBEAT_INTERVAL = 0.05


def _build_sse_app() -> FastAPI:
    app = FastAPI()

    @app.get("/sse")
    async def sse() -> StreamingResponse:
        buffer = ResilientStreamBuffer("sse-heartbeat-filter")

        async def feed() -> None:
            await buffer.append('data: {"type":"first"}\n\n')
            await asyncio.sleep(_HEARTBEAT_INTERVAL * 4)  # idle long enough for a keep-alive
            await buffer.append('data: {"type":"second"}\n\n')
            await buffer.end_stream()

        async def frames() -> AsyncIterator[str]:
            feeder = asyncio.create_task(feed())
            try:
                async for frame in buffer.subscribe(heartbeat_interval=_HEARTBEAT_INTERVAL):
                    yield frame
            finally:
                await feeder

        return StreamingResponse(frames(), media_type="text/event-stream")

    @app.get("/json")
    async def plain() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _stream_lines(client: TestClient) -> list[str]:
    with client.stream("GET", "/sse") as response:
        return list(response.iter_lines())


def _parse_events(lines: list[str]) -> list[object]:
    return [json.loads(line[6:]) for line in lines if line.startswith("data: ")]


def test_the_keep_alive_frame_is_what_breaks_a_naive_event_parser() -> None:
    with TestClient(_build_sse_app()) as client:
        lines = _stream_lines(client)

    assert "event: heartbeat" in lines
    assert None in _parse_events(lines)  # `data: null` is what crashed `data.get("type")`


def test_hidden_keep_alives_leave_only_application_events() -> None:
    with TestClient(_build_sse_app()) as client:
        client.event_hooks["response"].append(hide_sse_heartbeats)
        lines = _stream_lines(client)

    assert "event: heartbeat" not in lines
    assert [event["type"] for event in _parse_events(lines)] == ["first", "second"]


def test_non_sse_responses_are_untouched() -> None:
    with TestClient(_build_sse_app()) as client:
        client.event_hooks["response"].append(hide_sse_heartbeats)
        assert client.get("/json").json() == {"status": "ok"}


def test_drop_sse_heartbeats_keeps_the_frames_around_a_keep_alive_intact() -> None:
    lines = ["data: {}", "", "event: heartbeat", "data: null", "", "event: message", "data: {}", ""]

    assert list(drop_sse_heartbeats(iter(lines))) == ["data: {}", "", "event: message", "data: {}", ""]


def test_the_agent_client_fixture_registers_the_filter(client: TestClient) -> None:
    assert hide_sse_heartbeats in client.event_hooks["response"]


def _async_client(*, hidden: bool) -> httpx.AsyncClient:
    hooks = {"response": [hide_sse_heartbeats_async]} if hidden else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=_build_sse_app()), base_url="http://test", event_hooks=hooks)


async def _astream_lines(client: httpx.AsyncClient) -> list[str]:
    async with client.stream("GET", "/sse") as response:
        return [line async for line in response.aiter_lines()]


@pytest.mark.asyncio
async def test_an_async_client_meets_the_same_keep_alive_without_the_hook() -> None:
    async with _async_client(hidden=False) as client:
        lines = await _astream_lines(client)

    assert "event: heartbeat" in lines
    assert None in _parse_events(lines)


@pytest.mark.asyncio
async def test_hidden_keep_alives_leave_only_application_events_for_an_async_client() -> None:
    async with _async_client(hidden=True) as client:
        lines = await _astream_lines(client)
        plain = await client.get("/json")

    assert "event: heartbeat" not in lines
    assert [event["type"] for event in _parse_events(lines)] == ["first", "second"]
    assert plain.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_the_async_filter_drops_exactly_what_the_sync_filter_drops() -> None:
    lines = ["data: {}", "", "event: heartbeat", "data: null", "", "event: message", "data: {}", ""]

    async def source() -> AsyncIterator[str]:
        for line in lines:
            yield line

    assert [line async for line in adrop_sse_heartbeats(source())] == list(drop_sse_heartbeats(iter(lines)))
