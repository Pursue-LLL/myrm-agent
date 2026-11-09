"""A request signer runs on every attempt: a retry is signed afresh and a redirect hop is signed for its own address."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.toolkits.llms.transport.http import (
    Chunk,
    PreparedRequest,
    aopen_stream,
    asend_json,
    open_stream,
    send_json,
)

Handler = Callable[[httpx.Request], httpx.Response]
_URL = "https://gateway.example.test/v1/chat/completions"
_OK = {"ok": True}
_SSE = b'data: {"n": 1}\n\ndata: [DONE]\n\n'


@dataclass
class Net:
    requests: list[httpx.Request] = field(default_factory=list)
    handler: Handler = lambda request: httpx.Response(200, json=_OK)


@pytest.fixture
def net(monkeypatch: pytest.MonkeyPatch) -> Net:
    state = Net()

    def respond(request: httpx.Request) -> httpx.Response:
        state.requests.append(request)
        return state.handler(request)

    async def no_pause(seconds: float) -> None:
        return None

    monkeypatch.setattr(http, "_sync_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(http, "_pause", lambda seconds: None)
    monkeypatch.setattr(http, "_apause", no_pause)
    return state


class Signer:
    """Signs a request by stamping the ordinal of the attempt, its address and the digest of its body on it."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> None:
        self.seen.append(request)
        request.headers["x-signature"] = f"{len(self.seen)}|{request.url.path}|{len(request.content)}"


class _Decoder:
    def __init__(self) -> None:
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        if data == "[DONE]":
            self.done = True
            return []
        return [json.loads(data)]

    def finish(self) -> list[Chunk]:
        return []


def _request(signer: Signer | None, **overrides: object) -> PreparedRequest:
    fields: dict[str, object] = {
        "provider": "bedrock",
        "url": _URL,
        "headers": {"Content-Type": "application/json"},
        "body": {"model": "m", "messages": []},
        "timeout": 30.0,
        "retries": 2,
        "signer": signer,
    }
    fields.update(overrides)
    return PreparedRequest(**fields)  # type: ignore[arg-type]


def _call(mode: str, req: PreparedRequest) -> dict[str, object]:
    return send_json(req) if mode == "sync" else asyncio.run(asend_json(req))


def _stream(mode: str, req: PreparedRequest) -> list[Chunk]:
    if mode == "sync":
        return list(open_stream(req, _Decoder()))

    async def collect() -> list[Chunk]:
        return [chunk async for chunk in await aopen_stream(req, _Decoder())]

    return asyncio.run(collect())


def _answers(*first: httpx.Response) -> Handler:
    queue = list(first)
    return lambda request: queue.pop(0) if queue else httpx.Response(200, json=_OK)


@pytest.mark.parametrize("mode", ["sync", "async"])
class TestSigning:
    def test_the_signature_is_on_the_request_that_reaches_the_provider(self, net: Net, mode: str) -> None:
        signer = Signer()

        assert _call(mode, _request(signer)) == _OK

        (sent,) = net.requests
        assert sent.headers["x-signature"] == f"1|/v1/chat/completions|{len(sent.content)}"

    def test_the_signer_sees_the_final_bytes_and_the_json_content_type(self, net: Net, mode: str) -> None:
        signer = Signer()

        _call(mode, _request(signer, headers={}))

        (seen,) = signer.seen
        assert json.loads(seen.content) == {"model": "m", "messages": []}
        assert seen.headers["content-type"] == "application/json"

    def test_each_retry_is_signed_afresh(self, net: Net, mode: str) -> None:
        net.handler = _answers(httpx.Response(503, json={}), httpx.Response(429, json={}))
        signer = Signer()

        assert _call(mode, _request(signer)) == _OK

        assert [r.headers["x-signature"].split("|")[0] for r in net.requests] == ["1", "2", "3"]

    def test_a_redirect_hop_is_signed_for_the_address_it_moved_to(self, net: Net, mode: str) -> None:
        net.handler = _answers(httpx.Response(307, headers={"location": "https://gateway.example.test/v2/chat"}))
        signer = Signer()

        _call(mode, _request(signer))

        assert [r.headers["x-signature"] for r in net.requests] == [
            f"1|/v1/chat/completions|{len(net.requests[0].content)}",
            f"2|/v2/chat|{len(net.requests[1].content)}",
        ]

    def test_a_stream_is_signed_too(self, net: Net, mode: str) -> None:
        net.handler = lambda request: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_SSE)
        signer = Signer()

        assert _stream(mode, _request(signer, stream=True)) == [{"n": 1}]

        assert net.requests[0].headers["x-signature"].startswith("1|")

    def test_a_multipart_upload_is_signed_over_the_bytes_of_that_attempt(self, net: Net, mode: str) -> None:
        net.handler = _answers(httpx.Response(503, json={}))
        signer = Signer()

        upload = {"file": ("a.wav", b"RIFF-bytes", "audio/wav")}
        _call(mode, _request(signer, headers={}, body=None, form={"model": "m"}, files=upload))

        first, second = net.requests
        assert first.headers["x-signature"].endswith(f"|{len(first.content)}")
        assert second.headers["x-signature"].endswith(f"|{len(second.content)}")
        assert first.headers["content-type"] != second.headers["content-type"], "a fresh boundary per attempt"

    def test_a_request_without_a_signer_is_sent_as_it_is(self, net: Net, mode: str) -> None:
        _call(mode, _request(None))

        assert "x-signature" not in net.requests[0].headers
