"""What the transport retries before a provider has produced anything, how long it waits, and what it never repeats."""

from __future__ import annotations

import asyncio
import email.utils
import json
import time
from collections.abc import AsyncIterator, Callable, Iterator
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
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

Handler = Callable[[httpx.Request], httpx.Response]
_OK = {"ok": True}


@dataclass
class Net:
    """The requests that reached the fake provider and the pauses the retry loop asked for."""

    requests: list[httpx.Request] = field(default_factory=list)
    pauses: list[float] = field(default_factory=list)
    handler: Handler = lambda request: httpx.Response(200, json=_OK)


@pytest.fixture
def net(monkeypatch: pytest.MonkeyPatch) -> Net:
    state = Net()

    def respond(request: httpx.Request) -> httpx.Response:
        state.requests.append(request)
        return state.handler(request)

    async def apause(seconds: float) -> None:
        state.pauses.append(seconds)

    monkeypatch.setattr(http, "_sync_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(http, "_pause", state.pauses.append)
    monkeypatch.setattr(http, "_apause", apause)
    return state


def _request(retries: int = DEFAULT_RETRIES, **overrides: object) -> PreparedRequest:
    fields: dict[str, object] = {
        "provider": "openai",
        "url": "https://api.example.test/v1/chat/completions",
        "headers": {},
        "body": {"model": "m"},
        "timeout": 30.0,
        "retries": retries,
    }
    fields.update(overrides)
    return PreparedRequest(**fields)  # type: ignore[arg-type]


def _failing_first(failure: Callable[[], httpx.Response | Exception], times: int = 1) -> Handler:
    """Fail ``times`` requests with ``failure()``, then answer."""
    seen = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        if seen <= times:
            outcome = failure()
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return httpx.Response(200, json=_OK)

    return handler


class TestStatuses:
    @pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 529])
    def test_a_timeout_conflict_rate_limit_or_server_fault_is_tried_again(self, net: Net, status: int) -> None:
        net.handler = _failing_first(lambda: httpx.Response(status, json={"error": {"message": "later"}}))

        assert send_json(_request()) == _OK
        assert len(net.requests) == 2
        assert len(net.pauses) == 1

    @pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 413, 422])
    def test_a_refusal_the_provider_would_repeat_is_final(self, net: Net, status: int) -> None:
        net.handler = lambda request: httpx.Response(status, json={"error": {"message": "no"}})

        with pytest.raises(LLMHTTPError) as raised:
            send_json(_request())

        assert raised.value.status_code == status
        assert len(net.requests) == 1
        assert net.pauses == []

    def test_a_provider_that_stays_down_fails_after_the_retry_budget(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(503, json={"error": {"message": "down"}})

        with pytest.raises(LLMHTTPError) as raised:
            send_json(_request())

        assert raised.value.status_code == 503
        assert len(net.requests) == 1 + DEFAULT_RETRIES
        assert len(net.pauses) == DEFAULT_RETRIES

    def test_a_request_that_must_not_be_repeated_is_never_retried_on_a_status(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(503, json={})

        with pytest.raises(LLMHTTPError):
            send_json(_request(retries=0))

        assert len(net.requests) == 1

    def test_the_provider_can_overrule_the_status_either_way(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(503, headers={"x-should-retry": "false"}, json={})
        with pytest.raises(LLMHTTPError):
            send_json(_request())
        assert len(net.requests) == 1

        net.requests.clear()
        net.handler = _failing_first(lambda: httpx.Response(400, headers={"x-should-retry": "true"}, json={}))
        assert send_json(_request()) == _OK
        assert len(net.requests) == 2

    async def test_the_async_path_retries_the_same_way(self, net: Net) -> None:
        net.handler = _failing_first(lambda: httpx.Response(429, json={}), times=2)

        assert await asend_json(_request()) == _OK
        assert len(net.requests) == 3


class TestConnectionFailures:
    @pytest.mark.parametrize(
        "error",
        [
            httpx.ConnectError("refused"),
            httpx.ConnectTimeout("no route"),
            httpx.ReadError("reset"),
            httpx.WriteError("broken pipe"),
            httpx.PoolTimeout("busy"),
            httpx.RemoteProtocolError("closed without a response"),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_a_refused_or_dropped_connection_is_tried_again(self, net: Net, error: Exception) -> None:
        net.handler = _failing_first(lambda: error)

        assert send_json(_request()) == _OK
        assert len(net.requests) == 2

    @pytest.mark.parametrize("error", [httpx.ReadTimeout("silent"), httpx.WriteTimeout("stuck")], ids=type)
    @pytest.mark.parametrize("retries", [0, DEFAULT_RETRIES])
    def test_a_provider_that_stayed_silent_for_the_whole_limit_is_not_asked_again(
        self, net: Net, error: Exception, retries: int
    ) -> None:
        net.handler = _failing_first(lambda: error)

        with pytest.raises(type(error)):
            send_json(_request(retries=retries))

        assert len(net.requests) == 1
        assert net.pauses == []

    @pytest.mark.parametrize(
        "error",
        [httpx.UnsupportedProtocol("no scheme"), httpx.LocalProtocolError("bad header"), httpx.ProxyError("refused")],
        ids=lambda error: type(error).__name__,
    )
    def test_a_failure_another_attempt_cannot_change_is_final(self, net: Net, error: Exception) -> None:
        net.handler = _failing_first(lambda: error)

        with pytest.raises(type(error)):
            send_json(_request())

        assert len(net.requests) == 1

    def test_a_connection_that_never_opened_is_retried_once_even_for_a_request_that_must_not_repeat(
        self, net: Net
    ) -> None:
        net.handler = _failing_first(lambda: httpx.ConnectError("refused"))
        assert send_json(_request(retries=0)) == _OK
        assert len(net.requests) == 2

        net.requests.clear()
        net.handler = _failing_first(lambda: httpx.ConnectError("refused"), times=2)
        with pytest.raises(httpx.ConnectError):
            send_json(_request(retries=0))
        assert len(net.requests) == 2

    def test_every_retry_resends_the_whole_request(self, net: Net) -> None:
        net.handler = _failing_first(lambda: httpx.Response(503, json={}))

        send_json(_request(body={"model": "m", "text": "你好"}))

        assert [json.loads(r.content) for r in net.requests] == [{"model": "m", "text": "你好"}] * 2


class TestWaiting:
    def test_the_wait_doubles_from_half_a_second_with_a_quarter_of_jitter(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(503, json={})

        with pytest.raises(LLMHTTPError):
            send_json(_request(retries=4))

        first, second, third, fourth = net.pauses
        assert 0.375 <= first <= 0.5
        assert 0.75 <= second <= 1.0
        assert 1.5 <= third <= 2.0
        assert 3.0 <= fourth <= 4.0

    def test_the_wait_never_exceeds_eight_seconds(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(503, json={})

        with pytest.raises(LLMHTTPError):
            send_json(_request(retries=7))

        assert max(net.pauses) <= 8.0
        assert net.pauses[-1] >= 6.0

    @pytest.mark.parametrize(
        ("headers", "expected"),
        [
            ({"Retry-After": "3"}, 3.0),
            ({"Retry-After": "2.5"}, 2.5),
            ({"retry-after-ms": "1500"}, 1.5),
            ({"retry-after-ms": "1500", "Retry-After": "9"}, 1.5),
            ({"retry-after-ms": "soon", "Retry-After": "4"}, 4.0),
            ({"Retry-After": "8"}, 8.0),
        ],
        ids=["seconds", "fractional", "milliseconds", "ms-wins", "bad-ms-falls-back", "at-the-ceiling"],
    )
    def test_the_providers_own_boundary_is_waited_out(self, net: Net, headers: dict[str, str], expected: float) -> None:
        net.handler = _failing_first(lambda: httpx.Response(429, headers=headers, json={}))

        send_json(_request())

        assert net.pauses == [expected]

    def test_a_boundary_given_as_a_date_is_waited_out(self, net: Net) -> None:
        date = email.utils.formatdate(time.time() + 5, usegmt=True)
        net.handler = _failing_first(lambda: httpx.Response(429, headers={"Retry-After": date}, json={}))

        send_json(_request())

        (pause,) = net.pauses
        assert 3.5 <= pause <= 5.0

    @pytest.mark.parametrize(
        "headers",
        [{"Retry-After": "8.5"}, {"Retry-After": "60"}, {"Retry-After": "120"}, {"retry-after-ms": "9000"}],
        ids=["just-over", "a-minute", "two-minutes", "milliseconds"],
    )
    def test_a_boundary_beyond_the_backoff_ceiling_is_passed_up_instead_of_waited_out(
        self, net: Net, headers: dict[str, str]
    ) -> None:
        net.handler = lambda request: httpx.Response(429, headers=headers, json={})

        with pytest.raises(LLMHTTPError) as raised:
            send_json(_request())

        assert raised.value.status_code == 429
        assert len(net.requests) == 1
        assert net.pauses == []

    @pytest.mark.parametrize("value", ["0", "-3", "soon"], ids=["zero", "negative", "unreadable"])
    def test_a_boundary_that_says_nothing_leaves_the_backoff_alone(self, net: Net, value: str) -> None:
        net.handler = _failing_first(lambda: httpx.Response(429, headers={"Retry-After": value}, json={}))

        send_json(_request())

        (pause,) = net.pauses
        assert 0.375 <= pause <= 0.5

    async def test_cancelling_during_a_wait_stops_the_call_without_another_request(
        self, net: Net, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waiting = asyncio.Event()

        async def stall(seconds: float) -> None:
            waiting.set()
            await asyncio.sleep(3600)

        monkeypatch.setattr(http, "_apause", stall)
        net.handler = lambda request: httpx.Response(503, json={})

        task = asyncio.create_task(asend_json(_request()))
        await asyncio.wait_for(waiting.wait(), timeout=5)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(net.requests) == 1


class _ChunkDecoder:
    def __init__(self) -> None:
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        return [json.loads(data)]

    def finish(self) -> list[Chunk]:
        return []


class _Tracked(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A response body that notes whether it was released and optionally breaks after its first event."""

    def __init__(self, *, breaks: bool = False) -> None:
        self.closed = False
        self._breaks = breaks

    def __iter__(self) -> Iterator[bytes]:
        yield b'data: {"n": 1}\n\n'
        if self._breaks:
            raise httpx.ReadError("connection reset mid-stream")
        yield b'data: {"n": 2}\n\n'

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self:
            yield chunk

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.closed = True


class TestStreams:
    def test_a_stream_refused_before_it_begins_is_tried_again_and_the_refusal_is_released(self, net: Net) -> None:
        refused = _Tracked()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, stream=refused) if calls == 1 else httpx.Response(200, stream=_Tracked())

        net.handler = handler

        stream = open_stream(_request(stream=True), _ChunkDecoder())

        assert list(stream) == [{"n": 1}, {"n": 2}]
        assert len(net.requests) == 2
        assert refused.closed

    async def test_the_async_stream_does_the_same(self, net: Net) -> None:
        refused = _Tracked()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(429, stream=refused) if calls == 1 else httpx.Response(200, stream=_Tracked())

        net.handler = handler

        stream = await aopen_stream(_request(stream=True), _ChunkDecoder())

        assert [chunk async for chunk in stream] == [{"n": 1}, {"n": 2}]
        assert len(net.requests) == 2
        assert refused.closed

    def test_a_stream_that_breaks_after_it_began_is_never_started_over(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(200, stream=_Tracked(breaks=True))

        stream = open_stream(_request(stream=True), _ChunkDecoder())

        assert next(stream) == {"n": 1}
        with pytest.raises(httpx.ReadError):
            next(stream)
        assert len(net.requests) == 1
        assert net.pauses == []

    async def test_the_async_stream_that_breaks_after_it_began_is_never_started_over(self, net: Net) -> None:
        net.handler = lambda request: httpx.Response(200, stream=_Tracked(breaks=True))

        stream = await aopen_stream(_request(stream=True), _ChunkDecoder())

        assert await stream.__anext__() == {"n": 1}
        with pytest.raises(httpx.ReadError):
            await stream.__anext__()
        assert len(net.requests) == 1
