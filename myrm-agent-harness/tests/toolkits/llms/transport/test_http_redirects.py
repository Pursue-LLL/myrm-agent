"""Redirects of a model request: a gateway's 307/308 is followed on the configured host, every other one is reported."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError
from myrm_agent_harness.toolkits.llms.transport.http import (
    Chunk,
    PreparedRequest,
    aopen_stream,
    asend_json,
    open_stream,
    send_json,
)
from myrm_agent_harness.toolkits.llms.transport.redirects import MAX_REDIRECTS

Handler = Callable[[httpx.Request], httpx.Response]
_URL = "https://gateway.example.test/v1/chat/completions"
_OK = {"ok": True}
_SSE = b'data: {"n": 1}\n\ndata: [DONE]\n\n'


@dataclass
class Net:
    """The requests that reached the fake gateway and the handler that answers them."""

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


class _Decoder:
    """Decodes every framed event as one JSON object."""

    def __init__(self) -> None:
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        if data == "[DONE]":
            self.done = True
            return []
        return [json.loads(data)]

    def finish(self) -> list[Chunk]:
        return []


def _request(**overrides: object) -> PreparedRequest:
    fields: dict[str, object] = {
        "provider": "openai",
        "url": _URL,
        "headers": {"Authorization": "Bearer k", "x-api-key": "k"},
        "body": {"model": "m", "messages": []},
        "timeout": 30.0,
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
    """The given responses in order, then the plain answer."""
    queue = list(first)
    return lambda request: queue.pop(0) if queue else httpx.Response(200, json=_OK)


def _moved(status: int, location: str) -> httpx.Response:
    return httpx.Response(status, headers={"location": location})


@pytest.mark.parametrize("mode", ["sync", "async"])
class TestFollowed:
    @pytest.mark.parametrize("status", [307, 308])
    def test_a_method_keeping_redirect_on_the_same_host_arrives_with_the_call_intact(
        self, net: Net, mode: str, status: int
    ) -> None:
        net.handler = _answers(_moved(status, "https://gateway.example.test/openai/v1/chat/completions"))
        assert _call(mode, _request()) == _OK
        first, second = net.requests
        assert (second.method, str(second.url)) == ("POST", "https://gateway.example.test/openai/v1/chat/completions")
        assert second.content == first.content
        assert (second.headers["authorization"], second.headers["x-api-key"]) == ("Bearer k", "k")

    def test_a_relative_location_is_resolved_against_the_address_that_was_called(self, net: Net, mode: str) -> None:
        net.handler = _answers(_moved(308, "/openai/v1/chat/completions"))
        assert _call(mode, _request()) == _OK
        assert str(net.requests[1].url) == "https://gateway.example.test/openai/v1/chat/completions"

    def test_the_location_is_the_whole_address_so_the_original_query_is_not_added_to_it(
        self, net: Net, mode: str
    ) -> None:
        net.handler = _answers(_moved(307, "https://gateway.example.test/v2/chat?api-version=2"))
        _call(mode, _request(query={"api-version": "1", "extra": "x"}))
        first, second = net.requests
        assert first.url.params["api-version"] == "1"
        assert dict(second.url.params) == {"api-version": "2"}

    def test_a_plain_http_address_may_move_to_https_on_its_host_and_another_port(self, net: Net, mode: str) -> None:
        net.handler = _answers(_moved(308, "https://gateway.example.test:8443/v1/chat/completions"))
        assert _call(mode, _request(url="http://gateway.example.test:8080/v1/chat/completions")) == _OK
        assert str(net.requests[1].url) == "https://gateway.example.test:8443/v1/chat/completions"

    def test_the_log_line_of_a_hop_shows_no_secret_the_address_carries(
        self, net: Net, mode: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        net.handler = _answers(_moved(307, "https://user:hunter2@gateway.example.test/v2/chat?token=secret#frag"))
        with caplog.at_level(logging.WARNING, logger=http.logger.name):
            _call(mode, _request())
        assert "redirects to https://gateway.example.test/v2/chat" in caplog.text
        for secret in ("hunter2", "secret", "#frag"):
            assert secret not in caplog.text

    def test_a_hop_does_not_use_up_the_retry_budget(self, net: Net, mode: str) -> None:
        net.handler = _answers(_moved(307, _URL + "/moved"), httpx.Response(429, json={}))
        assert _call(mode, _request(retries=1)) == _OK
        assert len(net.requests) == 3

    def test_a_multipart_upload_is_sent_again_whole(self, net: Net, mode: str) -> None:
        net.handler = _answers(_moved(307, _URL + "/moved"))
        upload = {"file": ("a.wav", b"RIFF-bytes", "audio/wav")}
        _call(mode, _request(body=None, form={"model": "m"}, files=upload))
        first, second = net.requests
        assert b"RIFF-bytes" in second.content and b'name="model"' in second.content
        assert second.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert first.headers["content-type"].startswith("multipart/form-data; boundary=")

    def test_a_stream_follows_the_redirect_before_its_first_chunk(self, net: Net, mode: str) -> None:
        sse = httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_SSE)
        net.handler = _answers(_moved(307, _URL + "/moved"), sse)
        assert _stream(mode, _request(stream=True)) == [{"n": 1}]
        assert len(net.requests) == 2


@pytest.mark.parametrize("mode", ["sync", "async"])
class TestReported:
    @pytest.mark.parametrize(
        "location",
        [
            "https://other.example.test/v1/chat/completions",
            "https://gateway.example.test.evil.test/v1/chat/completions",
            "http://gateway.example.test/v1/chat/completions",
            "ftp://gateway.example.test/v1/chat/completions",
            "",
        ],
        ids=["another host", "a host that only starts like it", "https to http", "another scheme", "no address"],
    )
    @pytest.mark.parametrize("status", [307, 308])
    def test_a_redirect_that_would_move_the_credential_off_the_host_is_never_followed(
        self, net: Net, mode: str, status: int, location: str
    ) -> None:
        net.handler = lambda request: _moved(status, location)
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request())
        assert caught.value.status_code == status
        assert [request.url.host for request in net.requests] == ["gateway.example.test"]

    def test_a_plain_http_call_is_not_sent_on_to_an_address_that_is_not_a_web_address(
        self, net: Net, mode: str
    ) -> None:
        net.handler = lambda request: _moved(307, "ftp://gateway.example.test/v1/chat/completions")
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request(url="http://gateway.example.test/v1/chat/completions"))
        assert caught.value.status_code == 307
        assert len(net.requests) == 1

    @pytest.mark.parametrize("status", [301, 302, 303])
    def test_a_redirect_that_turns_the_call_into_a_get_is_reported_not_followed(
        self, net: Net, mode: str, status: int
    ) -> None:
        net.handler = lambda request: _moved(status, _URL + "/moved")
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request())
        assert caught.value.status_code == status
        assert len(net.requests) == 1

    def test_a_redirect_without_an_address_is_an_answer_like_any_other(self, net: Net, mode: str) -> None:
        net.handler = lambda request: httpx.Response(307)
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request())
        assert caught.value.status_code == 307
        assert len(net.requests) == 1

    def test_a_redirect_loop_stops_after_the_hop_limit(self, net: Net, mode: str) -> None:
        def loop(request: httpx.Request) -> httpx.Response:
            # A transport that does not cut the loop fails here instead of hanging the suite.
            assert len(net.requests) <= MAX_REDIRECTS + 2, "the redirect loop was not cut"
            return _moved(307, _URL)

        net.handler = loop
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request())
        assert caught.value.status_code == 307
        assert len(net.requests) == MAX_REDIRECTS + 1

    def test_the_failure_names_where_it_pointed_without_a_secret_the_address_carries(self, net: Net, mode: str) -> None:
        net.handler = lambda request: _moved(307, "https://user:hunter2@other.example.test/v1/chat?token=secret#frag")
        with pytest.raises(LLMHTTPError, match=r"redirected to https://other\.example\.test/v1/chat") as caught:
            _call(mode, _request())
        for secret in ("hunter2", "secret", "frag"):
            assert secret not in str(caught.value)
        assert "base URL" in str(caught.value)

    def test_an_empty_location_says_that_no_address_was_given(self, net: Net, mode: str) -> None:
        net.handler = lambda request: _moved(308, "")
        with pytest.raises(LLMHTTPError, match="redirected without an address the transport can use"):
            _call(mode, _request())

    def test_the_page_a_proxy_sends_with_its_redirect_is_not_the_message(self, net: Net, mode: str) -> None:
        page = httpx.Response(
            301, headers={"location": "https://other.example.test/x"}, content=b"<html>Moved Permanently</html>"
        )
        net.handler = lambda request: page
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request())
        assert "<html>" not in str(caught.value)

    def test_an_answer_that_is_not_a_redirect_keeps_the_providers_own_words(self, net: Net, mode: str) -> None:
        net.handler = lambda request: httpx.Response(400, json={"error": {"message": "bad model"}})
        with pytest.raises(LLMHTTPError) as caught:
            _call(mode, _request())
        assert caught.value.body == {"error": {"message": "bad model"}}
        assert "bad model" in str(caught.value)
