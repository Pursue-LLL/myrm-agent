"""A model call from a new event loop succeeds after the loop of an earlier call has closed.

[INPUT]
- tests.support.live_chat_model::live_chat_model (POS: the helper under test)

[OUTPUT]
- test_each_event_loop_gets_a_client_of_its_own: three calls, one event loop each, all answered
- test_the_model_carries_the_settings_it_was_given: model, sampling, output cap, timeout, endpoint and key reach the model
- test_the_client_is_closed_when_the_block_ends: no connection outlives the test that opened it

[POS]
Guards the helper's one job. Against a server that keeps connections open, a plain ``ChatOpenAI`` answers its first call
and fails the second, made from a new event loop, with ``Event loop is closed``; the helper must answer every one.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import SecretStr

from tests.support.live_chat_model import live_chat_model

_REPLY = json.dumps(
    {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "probe",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
).encode()


class _ChatCompletions(BaseHTTPRequestHandler):
    # HTTP/1.1 keeps the connection open between requests, which is what lets a pooled connection outlive its event loop.
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(_REPLY)))
        self.end_headers()
        self.wfile.write(_REPLY)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of one access line per request."""


@pytest.fixture
def provider_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ChatCompletions)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # A system proxy would carry the request away from the local server.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


async def _ask(base_url: str) -> str:
    async with live_chat_model(model="probe", api_key="unused", base_url=base_url) as chat:
        return str((await chat.ainvoke("hi")).content)


def test_each_event_loop_gets_a_client_of_its_own(provider_url: str) -> None:
    # Each asyncio.run is one test's event loop: opened for the call and closed after it, as pytest-asyncio does per test.
    assert [asyncio.run(_ask(provider_url)) for _ in range(3)] == ["ok", "ok", "ok"]


async def test_the_model_carries_the_settings_it_was_given() -> None:
    async with live_chat_model(
        model="m", api_key="k", base_url="http://127.0.0.1:1/v1", temperature=0, max_tokens=512, timeout=60
    ) as chat:
        assert (chat.model_name, chat.temperature, chat.max_tokens, chat.request_timeout) == ("m", 0, 512, 60)
        assert chat.openai_api_base == "http://127.0.0.1:1/v1"
        assert isinstance(chat.openai_api_key, SecretStr)
        assert chat.openai_api_key.get_secret_value() == "k"


async def test_the_client_is_closed_when_the_block_ends() -> None:
    async with live_chat_model(model="m", api_key="k", base_url=None) as chat:
        client = chat.http_async_client
        assert client is not None
        assert not client.is_closed

    assert client.is_closed
