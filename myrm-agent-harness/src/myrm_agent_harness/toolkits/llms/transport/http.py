"""HTTP execution for the model transport: shared clients, one request/stream round trip, SSE framing.

[INPUT]
- httpx (POS: the HTTP client; proxy and TLS behavior come from it and from infra.tls_compat)
- transport.errors (POS: LLMHTTPError for failed statuses)

[OUTPUT]
- PreparedRequest: one fully built provider request (what a wire module produces)
- StreamDecoder: the contract a wire module implements to turn SSE events / NDJSON lines into chat chunks
- send_json / asend_json: one non-streaming round trip, parsed
- open_stream / aopen_stream: one streaming round trip, as a chunk iterator
- ProviderStream / AsyncProviderStream: chunk iterators that remember the finish reason the provider reported

[POS]
The only place the transport touches the network. A wire module builds a PreparedRequest and a decoder; this module
sends it, maps a failed status to LLMHTTPError, retries a refused connection once (the request never reached the
provider) and nothing else, so the agent layer stays the single retry authority. Clients are shared per event loop
and egress proxy; the per-request timeout is the provider's silence budget, as a stream that keeps producing is not cut.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol

import httpx

from myrm_agent_harness.toolkits.llms.transport.errors import araise_for_status, raise_for_status

_LIMITS: Final = httpx.Limits(max_connections=200, max_keepalive_connections=50, keepalive_expiry=30.0)
_ASYNC_CLIENTS: dict[int, tuple[asyncio.AbstractEventLoop, dict[str | None, httpx.AsyncClient]]] = {}
_SYNC_CLIENTS: dict[str | None, httpx.Client] = {}
_SYNC_LOCK: Final = threading.Lock()

Chunk = dict[str, object]


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """One provider request, fully built and ready to send."""

    provider: str
    url: str
    headers: Mapping[str, str]
    body: Mapping[str, object] | None
    timeout: float | None
    proxy: str | None = None
    stream: bool = False
    query: Mapping[str, str] = field(default_factory=dict)
    framing: str = "sse"  # "sse" or "ndjson"


class StreamDecoder(Protocol):
    """Turns the framed stream of one provider into OpenAI-shaped chat chunks."""

    done: bool

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        """Chunks carried by one SSE event / NDJSON line (may be empty)."""
        ...

    def finish(self) -> list[Chunk]:
        """Chunks still owed when the stream ends (empty for stateless decoders)."""
        ...


def _timeout(seconds: float | None) -> httpx.Timeout:
    return httpx.Timeout(seconds)


def _async_client(proxy: str | None) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    for key, (known, _) in list(_ASYNC_CLIENTS.items()):
        if known.is_closed():
            del _ASYNC_CLIENTS[key]
    _, clients = _ASYNC_CLIENTS.setdefault(id(loop), (loop, {}))
    client = clients.get(proxy)
    if client is None or client.is_closed:
        client = clients[proxy] = httpx.AsyncClient(proxy=proxy, limits=_LIMITS, timeout=_timeout(None))
    return client


def _sync_client(proxy: str | None) -> httpx.Client:
    with _SYNC_LOCK:
        client = _SYNC_CLIENTS.get(proxy)
        if client is None or client.is_closed:
            client = _SYNC_CLIENTS[proxy] = httpx.Client(proxy=proxy, limits=_LIMITS, timeout=_timeout(None))
        return client


def _build(client: httpx.Client | httpx.AsyncClient, req: PreparedRequest) -> httpx.Request:
    return client.build_request(
        "POST",
        req.url,
        params=dict(req.query) or None,
        headers=dict(req.headers),
        content=json.dumps(req.body, ensure_ascii=False).encode() if req.body is not None else None,
        timeout=_timeout(req.timeout),
    )


def _with_json_headers(req: PreparedRequest) -> PreparedRequest:
    if any(k.lower() == "content-type" for k in req.headers):
        return req
    return PreparedRequest(
        provider=req.provider,
        url=req.url,
        headers={**req.headers, "Content-Type": "application/json"},
        body=req.body,
        timeout=req.timeout,
        proxy=req.proxy,
        stream=req.stream,
        query=req.query,
        framing=req.framing,
    )


def _send(req: PreparedRequest) -> httpx.Response:
    client = _sync_client(req.proxy)
    request = _build(client, req)
    try:
        return client.send(request, stream=req.stream)
    except httpx.ConnectError:
        return client.send(_build(client, req), stream=req.stream)


async def _asend(req: PreparedRequest) -> httpx.Response:
    client = _async_client(req.proxy)
    request = _build(client, req)
    try:
        return await client.send(request, stream=req.stream)
    except httpx.ConnectError:
        return await client.send(_build(client, req), stream=req.stream)


def _json_payload(response: httpx.Response, provider: str) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(f"{provider} answered with a non-JSON body: {response.text[:200]!r}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{provider} answered with a non-object JSON body")
    return payload


def send_json(req: PreparedRequest) -> dict[str, object]:
    """One non-streaming round trip; the parsed JSON object of a 2xx answer."""
    req = _with_json_headers(req)
    response = _send(req)
    try:
        raise_for_status(response, req.provider)
        return _json_payload(response, req.provider)
    finally:
        response.close()


async def asend_json(req: PreparedRequest) -> dict[str, object]:
    """Async twin of :func:`send_json`."""
    req = _with_json_headers(req)
    response = await _asend(req)
    try:
        await araise_for_status(response, req.provider)
        return _json_payload(response, req.provider)
    finally:
        await response.aclose()


# --- stream framing ------------------------------------------------------------------------------------------


class _SseParser:
    """Line-by-line SSE state machine: ``push`` returns an event when a blank line closes one."""

    __slots__ = ("_data", "_event")

    def __init__(self) -> None:
        self._event: str | None = None
        self._data: list[str] = []

    def push(self, line: str) -> tuple[str | None, str] | None:
        if not line:
            return self.flush()
        if line.startswith(":"):
            return None
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event = value
        return None

    def flush(self) -> tuple[str | None, str] | None:
        event, data = self._event, self._data
        self._event, self._data = None, []
        return (event, "\n".join(data)) if data else None


def _iter_events(lines: Iterator[str], framing: str) -> Iterator[tuple[str | None, str]]:
    if framing == "ndjson":
        for line in lines:
            if line.strip():
                yield None, line
        return
    parser = _SseParser()
    for line in lines:
        if (event := parser.push(line)) is not None:
            yield event
    if (event := parser.flush()) is not None:
        yield event


async def _aiter_events(lines: AsyncIterator[str], framing: str) -> AsyncIterator[tuple[str | None, str]]:
    if framing == "ndjson":
        async for line in lines:
            if line.strip():
                yield None, line
        return
    parser = _SseParser()
    async for line in lines:
        if (event := parser.push(line)) is not None:
            yield event
    if (event := parser.flush()) is not None:
        yield event


def _finish_reason(chunk: Chunk) -> str | None:
    choices = chunk.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reason = choices[0].get("finish_reason")
        return reason if isinstance(reason, str) and reason else None
    return None


class ProviderStream:
    """Sync chunk iterator; ``received_finish_reason`` is what the provider itself reported, never a guess."""

    def __init__(self, response: httpx.Response, decoder: StreamDecoder, framing: str) -> None:
        self.received_finish_reason: str | None = None
        self._chunks = self._generate(response, decoder, framing)

    def __iter__(self) -> ProviderStream:
        return self

    def __next__(self) -> Chunk:
        return next(self._chunks)

    def close(self) -> None:
        self._chunks.close()

    def _generate(self, response: httpx.Response, decoder: StreamDecoder, framing: str) -> Generator[Chunk]:
        try:
            for event, data in _iter_events(response.iter_lines(), framing):
                for chunk in decoder.feed(event, data):
                    self.received_finish_reason = _finish_reason(chunk) or self.received_finish_reason
                    yield chunk
                if decoder.done:
                    break
            for chunk in decoder.finish():
                self.received_finish_reason = _finish_reason(chunk) or self.received_finish_reason
                yield chunk
        finally:
            response.close()


class AsyncProviderStream:
    """Async twin of :class:`ProviderStream`."""

    def __init__(self, response: httpx.Response, decoder: StreamDecoder, framing: str) -> None:
        self.received_finish_reason: str | None = None
        self._chunks = self._generate(response, decoder, framing)

    def __aiter__(self) -> AsyncProviderStream:
        return self

    async def __anext__(self) -> Chunk:
        return await self._chunks.__anext__()

    async def aclose(self) -> None:
        await self._chunks.aclose()

    async def _generate(self, response: httpx.Response, decoder: StreamDecoder, framing: str) -> AsyncGenerator[Chunk]:
        try:
            async for event, data in _aiter_events(response.aiter_lines(), framing):
                for chunk in decoder.feed(event, data):
                    self.received_finish_reason = _finish_reason(chunk) or self.received_finish_reason
                    yield chunk
                if decoder.done:
                    break
            for chunk in decoder.finish():
                self.received_finish_reason = _finish_reason(chunk) or self.received_finish_reason
                yield chunk
        finally:
            await response.aclose()


def open_stream(req: PreparedRequest, decoder: StreamDecoder) -> ProviderStream:
    """Send a streaming request; raises LLMHTTPError before any chunk when the provider refuses it."""
    req = _with_json_headers(req)
    response = _send(req)
    try:
        raise_for_status(response, req.provider)
    except BaseException:
        response.close()
        raise
    return ProviderStream(response, decoder, req.framing)


async def aopen_stream(req: PreparedRequest, decoder: StreamDecoder) -> AsyncProviderStream:
    """Async twin of :func:`open_stream`."""
    req = _with_json_headers(req)
    response = await _asend(req)
    try:
        await araise_for_status(response, req.provider)
    except BaseException:
        await response.aclose()
        raise
    return AsyncProviderStream(response, decoder, req.framing)
