"""One request/stream round trip: SSE and NDJSON framing, status mapping, header rules (retries: test_http_retry)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterator

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError
from myrm_agent_harness.toolkits.llms.transport.http import (
    Chunk,
    PreparedRequest,
    aclose_clients,
    aopen_stream,
    asend_json,
    open_stream,
    send_json,
)

Handler = Callable[[httpx.Request], httpx.Response]


class _JsonLineDecoder:
    """Decodes every framed event as one JSON object, the way the OpenAI wire does."""

    def __init__(self) -> None:
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        if data == "[DONE]":
            self.done = True
            return []
        return [json.loads(data)]

    def finish(self) -> list[Chunk]:
        return []


class _NamedEventDecoder(_JsonLineDecoder):
    """Also records the event name each framed event arrived under."""

    def __init__(self) -> None:
        super().__init__()
        self.names: list[str | None] = []

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        self.names.append(event)
        return super().feed(event, data)


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Handler], list[httpx.Request]]]:
    """Route every request through a handler; ``arm(handler)`` returns the list the requests land in."""
    seen: list[httpx.Request] = []
    handlers: list[Handler] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handlers[0](request)

    monkeypatch.setattr(http, "_sync_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    def arm(handler: Handler) -> list[httpx.Request]:
        handlers[:] = [handler]
        return seen

    yield arm


def _request(**overrides: object) -> PreparedRequest:
    fields: dict[str, object] = {
        "provider": "openai",
        "url": "https://api.example.test/v1/chat/completions",
        "headers": {"Authorization": "Bearer k"},
        "body": {"model": "m", "messages": []},
        "timeout": 30.0,
    }
    fields.update(overrides)
    return PreparedRequest(**fields)  # type: ignore[arg-type]


_SSE = (
    'data: {"n": 1}\n\n'
    ": comment line\n\n"
    "event: custom\n"
    'data: {"n": 2}\n\n'
    "data: [DONE]\n\n"
    'data: {"after_done": true}\n\n'
)


class TestSendJson:
    def test_posts_json_with_the_content_type_added_and_returns_the_object(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        seen = network(lambda request: httpx.Response(200, json={"ok": True}))
        assert send_json(_request(query={"api-version": "1"})) == {"ok": True}
        (request,) = seen
        assert request.headers["content-type"] == "application/json"
        assert request.headers["authorization"] == "Bearer k"
        assert request.url.params["api-version"] == "1"
        assert json.loads(request.content) == {"model": "m", "messages": []}

    def test_non_ascii_text_goes_out_as_utf8_not_escapes(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        seen = network(lambda request: httpx.Response(200, json={}))
        send_json(_request(body={"text": "你好"}))
        assert "你好".encode() in seen[0].content

    def test_a_caller_content_type_is_kept(self, network: Callable[[Handler], list[httpx.Request]]) -> None:
        seen = network(lambda request: httpx.Response(200, json={}))
        send_json(_request(headers={"content-type": "application/vnd.x+json"}))
        assert seen[0].headers["content-type"] == "application/vnd.x+json"

    def test_a_failed_status_raises_with_the_provider_body(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(429, json={"error": {"message": "slow"}}))
        with pytest.raises(LLMHTTPError) as caught:
            send_json(_request())
        assert (caught.value.status_code, caught.value.body) == (429, {"error": {"message": "slow"}})

    @pytest.mark.parametrize("content", [b"<html>", b"[1, 2]"])
    def test_a_2xx_answer_that_is_not_a_json_object_is_rejected(
        self, network: Callable[[Handler], list[httpx.Request]], content: bytes
    ) -> None:
        network(lambda request: httpx.Response(200, content=content))
        with pytest.raises(ValueError, match="openai answered"):
            send_json(_request())

    def test_a_multipart_request_carries_its_own_boundary_content_type(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        seen = network(lambda request: httpx.Response(200, json={}))
        send_json(_request(body=None, form={"prompt": "p"}, files={"image": ("a.png", b"\x89PNG", "image/png")}))
        assert seen[0].headers["content-type"].startswith("multipart/form-data; boundary=")

    async def test_async_twin(self, network: Callable[[Handler], list[httpx.Request]]) -> None:
        network(lambda request: httpx.Response(200, json={"ok": 1}))
        assert await asend_json(_request()) == {"ok": 1}

    async def test_async_twin_raises_a_failed_status_with_the_provider_body(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(429, json={"error": {"message": "slow"}}))
        with pytest.raises(LLMHTTPError) as caught:
            await asend_json(_request())
        assert (caught.value.status_code, caught.value.body) == (429, {"error": {"message": "slow"}})

    async def test_async_twin_tries_a_connection_that_never_opened_once_more(
        self, network: Callable[[Handler], list[httpx.Request]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pauses: list[float] = []

        async def apause(seconds: float) -> None:
            pauses.append(seconds)

        def refuse_once(request: httpx.Request) -> httpx.Response:
            if len(seen) == 1:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={"ok": 1})

        monkeypatch.setattr(http, "_apause", apause)
        seen = network(refuse_once)

        assert await asend_json(_request()) == {"ok": 1}
        assert len(seen) == 2
        assert len(pauses) == 1


class TestStreaming:
    def test_sse_events_are_framed_comments_dropped_and_the_stream_stops_at_done(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=_SSE.encode()))
        assert list(open_stream(_request(stream=True), _JsonLineDecoder())) == [{"n": 1}, {"n": 2}]

    def test_comment_lines_are_dropped_and_data_lines_of_one_event_are_joined(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        body = 'data: {"a":\ndata: 1}\n\n: ping\n\ndata: [DONE]\n\n'
        network(lambda request: httpx.Response(200, content=body.encode()))
        assert list(open_stream(_request(stream=True), _JsonLineDecoder())) == [{"a": 1}]

    def test_event_fields_other_than_data_and_event_are_not_taken_for_an_event_name(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        body = 'id: 7\nretry: 3000\ndata: {"n": 1}\n\nid: 8\nevent: custom\ndata: {"n": 2}\n\n'
        network(lambda request: httpx.Response(200, content=body.encode()))
        decoder = _NamedEventDecoder()

        assert list(open_stream(_request(stream=True), decoder)) == [{"n": 1}, {"n": 2}]
        assert decoder.names == [None, "custom"]

    def test_a_final_event_without_a_trailing_blank_line_is_still_delivered(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=b'data: {"n": 1}'))
        assert list(open_stream(_request(stream=True), _JsonLineDecoder())) == [{"n": 1}]

    def test_ndjson_framing_decodes_one_object_per_line_and_skips_blank_lines(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=b'{"n": 1}\n\n{"n": 2}\n'))
        stream = open_stream(_request(stream=True, framing="ndjson"), _JsonLineDecoder())
        assert list(stream) == [{"n": 1}, {"n": 2}]

    def test_the_finish_reason_is_remembered_only_when_the_provider_sent_one(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        body = (
            'data: {"choices": [{"delta": {"content": "a"}, "finish_reason": null}]}\n\n'
            'data: {"choices": [{"delta": {}, "finish_reason": "length"}]}\n\n'
            'data: {"choices": [], "usage": {}}\n\n'
        )
        network(lambda request: httpx.Response(200, content=body.encode()))
        stream = open_stream(_request(stream=True), _JsonLineDecoder())
        assert stream.received_finish_reason is None
        list(stream)
        assert stream.received_finish_reason == "length"

    def test_a_cut_stream_reports_no_finish_reason(self, network: Callable[[Handler], list[httpx.Request]]) -> None:
        body = 'data: {"choices": [{"delta": {"content": "a"}, "finish_reason": null}]}\n\n'
        network(lambda request: httpx.Response(200, content=body.encode()))
        stream = open_stream(_request(stream=True), _JsonLineDecoder())
        list(stream)
        assert stream.received_finish_reason is None

    def test_a_refused_stream_raises_before_any_chunk(self, network: Callable[[Handler], list[httpx.Request]]) -> None:
        network(lambda request: httpx.Response(400, json={"error": {"message": "bad request"}}))
        with pytest.raises(LLMHTTPError) as caught:
            open_stream(_request(stream=True), _JsonLineDecoder())
        assert caught.value.status_code == 400

    async def test_async_stream_matches_the_sync_one(self, network: Callable[[Handler], list[httpx.Request]]) -> None:
        body = 'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\ndata: [DONE]\n\n'
        network(lambda request: httpx.Response(200, content=body.encode()))
        stream = await aopen_stream(_request(stream=True), _JsonLineDecoder())
        chunks = [chunk async for chunk in stream]
        assert chunks == [{"choices": [{"delta": {}, "finish_reason": "stop"}]}]
        assert stream.received_finish_reason == "stop"

    async def test_async_refusal_raises_before_any_chunk(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(401, json={"error": {"message": "no key"}}))
        with pytest.raises(LLMHTTPError):
            await aopen_stream(_request(stream=True), _JsonLineDecoder())

    def test_closing_a_stream_early_releases_the_connection(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=b'data: {"n": 1}\n\ndata: {"n": 2}\n\n'))
        stream = open_stream(_request(stream=True), _JsonLineDecoder())
        assert next(stream) == {"n": 1}
        stream.close()
        with pytest.raises(StopIteration):
            next(stream)

    async def test_async_ndjson_framing_decodes_one_object_per_line_and_skips_blank_lines(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=b'{"n": 1}\n\n{"n": 2}\n'))
        stream = await aopen_stream(_request(stream=True, framing="ndjson"), _JsonLineDecoder())
        assert [chunk async for chunk in stream] == [{"n": 1}, {"n": 2}]

    async def test_async_final_event_without_a_trailing_blank_line_is_still_delivered(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=b'data: {"n": 1}'))
        stream = await aopen_stream(_request(stream=True), _JsonLineDecoder())
        assert [chunk async for chunk in stream] == [{"n": 1}]

    async def test_closing_an_async_stream_early_ends_it(
        self, network: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        network(lambda request: httpx.Response(200, content=b'data: {"n": 1}\n\ndata: {"n": 2}\n\n'))
        stream = await aopen_stream(_request(stream=True), _JsonLineDecoder())
        assert await anext(stream) == {"n": 1}
        await stream.aclose()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)


class TestSharedClients:
    async def test_closing_forgets_the_clients_so_the_next_request_builds_a_new_one(self) -> None:
        await aclose_clients()
        first = http._async_client(None)
        sync_first = http._sync_client(None)

        await aclose_clients()

        assert first.is_closed
        assert sync_first.is_closed
        assert http._async_client(None) is not first
        assert http._sync_client(None) is not sync_first
        await aclose_clients()

    async def test_clients_of_another_loop_are_forgotten_not_closed(self) -> None:
        await aclose_clients()
        other_loop = asyncio.new_event_loop()
        try:
            foreign = httpx.AsyncClient()
            http._ASYNC_CLIENTS[id(other_loop)] = (other_loop, {None: foreign})

            await aclose_clients()

            assert not foreign.is_closed
            assert id(other_loop) not in http._ASYNC_CLIENTS
        finally:
            other_loop.close()
            await foreign.aclose()


class TestPauses:
    """The wait between two attempts is a real sleep of the length the retry policy chose."""

    def test_the_pause_sleeps_for_the_given_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr(time, "sleep", slept.append)

        http._pause(1.5)

        assert slept == [1.5]

    async def test_the_async_pause_yields_to_the_loop_for_the_given_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []

        async def record(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", record)

        await http._apause(2.0)

        assert slept == [2.0]
