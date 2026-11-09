"""HTTP execution for the model transport: shared clients, one request/stream round trip, stream iterators.

[INPUT]
- httpx (POS: the HTTP client; proxy and TLS behavior come from it and from infra.tls_compat)
- transport.errors (POS: LLMHTTPError for failed statuses)
- transport.redirects (POS: which redirects are followed, within which host)
- transport.retry (POS: which failures are retried and how long to wait)
- transport.stream_events (POS: the events of a streamed body, whatever its framing)

[OUTPUT]
- PreparedRequest: one fully built provider request (what a wire module produces)
- StreamDecoder: the contract a wire module implements to turn stream events into chat chunks
- send_json / asend_json: one non-streaming round trip (JSON or multipart form body), parsed
- open_stream / aopen_stream: one streaming round trip, as a chunk iterator
- ProviderStream / AsyncProviderStream: chunk iterators that remember the finish reason the provider reported
- finish_reason_of: the finish reason one chat chunk carries, if any
- aclose_clients: closes and forgets every shared client (shutdown; tests)
- retire_clients: forgets every shared client without closing it, so the next request builds its client under the TLS
  and proxy settings then in force while a request still using one finishes undisturbed

[POS]
The only place the transport touches the network. A wire module builds a PreparedRequest and a decoder; this module
sends it, maps a failed status to LLMHTTPError and, for a request that allows it, retries what failed before the
provider produced anything (see transport.retry). A stream is never retried once it has begun. A 307/308 from a gateway
on the configured host is followed with the same body and headers (see transport.redirects); a hop is not a retry.
Clients are shared per event loop and egress proxy; the per-request timeout is the provider's silence budget, as a
stream that keeps producing is not cut.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncGenerator, Generator, Mapping
from dataclasses import dataclass, field, replace
from typing import Final, Protocol

import httpx

from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError, araise_for_status, raise_for_status
from myrm_agent_harness.toolkits.llms.transport.redirects import MAX_REDIRECTS, followed_url, shown
from myrm_agent_harness.toolkits.llms.transport.retry import answer_wait, error_wait
from myrm_agent_harness.toolkits.llms.transport.stream_events import aiter_stream_events, iter_stream_events

logger = logging.getLogger(__name__)

_LIMITS: Final = httpx.Limits(max_connections=200, max_keepalive_connections=50, keepalive_expiry=30.0)
_ASYNC_CLIENTS: dict[int, tuple[asyncio.AbstractEventLoop, dict[str | None, httpx.AsyncClient]]] = {}
_SYNC_CLIENTS: dict[str | None, httpx.Client] = {}
_SYNC_LOCK: Final = threading.Lock()

Chunk = dict[str, object]
# One multipart file field: ``(filename, content, mime)``, or a bare string for a field that only forces the
# multipart encoding.
FilePart = tuple[str, bytes, str] | str


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
    framing: str = "sse"  # "sse", "ndjson" or "eventstream" (see transport.stream_events)
    # A multipart request carries text fields in ``form`` and uploads in ``files`` instead of a JSON ``body``.
    form: Mapping[str, str] | None = None
    files: Mapping[str, FilePart] | None = None
    # Retries after the first attempt for a failure before anything came back; 0 for a call that must not be repeated.
    retries: int = 0


class StreamDecoder(Protocol):
    """Turns the framed stream of one provider into OpenAI-shaped chat chunks."""

    @property
    def done(self) -> bool:
        """True once the provider has said the stream is over; the framing layer stops reading there."""
        ...

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        """Chunks carried by one stream event (an SSE event, an NDJSON line or an event-stream message); may be empty."""
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
            # ``pop``: another thread's ``retire_clients`` may have emptied the registry since the snapshot.
            _ASYNC_CLIENTS.pop(key, None)
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


async def aclose_clients() -> None:
    """Close and forget every shared client.

    For the end of the process, and for a test that must not leave a connection behind. Closing aborts a request that
    is still being read, so a running process that changes its TLS policy calls ``retire_clients`` instead. Clients of
    another event loop cannot be closed from this one and are only forgotten.
    """
    running = asyncio.get_running_loop()
    entries = list(_ASYNC_CLIENTS.values())
    _ASYNC_CLIENTS.clear()
    with _SYNC_LOCK:
        sync_clients = list(_SYNC_CLIENTS.values())
        _SYNC_CLIENTS.clear()
    for loop, clients in entries:
        if loop is running:
            for client in clients.values():
                await client.aclose()
    for sync_client in sync_clients:
        sync_client.close()


def retire_clients() -> None:
    """Forget every shared client without closing it, so the next request builds a new one.

    A client keeps the TLS context it was built with, so a running process that changes its TLS or proxy policy calls
    this to have the next request follow the change. A request that is still using a client (a stream being read)
    holds its own reference and finishes on it; the client is collected once nothing refers to it.
    """
    _ASYNC_CLIENTS.clear()
    with _SYNC_LOCK:
        _SYNC_CLIENTS.clear()


def _build(client: httpx.Client | httpx.AsyncClient, req: PreparedRequest) -> httpx.Request:
    if req.files is not None:
        return client.build_request(
            "POST",
            req.url,
            params=dict(req.query) or None,
            headers=dict(req.headers),
            data=dict(req.form or {}),
            files=dict(req.files),
            timeout=_timeout(req.timeout),
        )
    return client.build_request(
        "POST",
        req.url,
        params=dict(req.query) or None,
        headers=dict(req.headers),
        content=json.dumps(req.body, ensure_ascii=False).encode() if req.body is not None else None,
        timeout=_timeout(req.timeout),
    )


def _with_json_headers(req: PreparedRequest) -> PreparedRequest:
    """A multipart request keeps no Content-Type here: the client adds it with the boundary."""
    if req.files is not None or any(k.lower() == "content-type" for k in req.headers):
        return req
    return replace(req, headers={**req.headers, "Content-Type": "application/json"})


def _pause(seconds: float) -> None:
    time.sleep(seconds)


async def _apause(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _log_retry(req: PreparedRequest, retried: int, wait: float, reason: str) -> None:
    logger.warning("Retrying %s request in %.1fs (retry %d) after %s", req.provider, wait, retried, reason)


def _redirected(req: PreparedRequest, response: httpx.Response, hops: int) -> PreparedRequest | None:
    """The request a redirect answer moves the call to; ``None`` when the answer is the final one.

    The location is the whole address, so the request's own query is not added to it.
    """
    target = followed_url(response) if hops < MAX_REDIRECTS else None
    if target is None:
        return None
    logger.warning(
        "%s endpoint answered HTTP %d and redirects to %s", req.provider, response.status_code, shown(target)
    )
    return replace(req, url=str(target), query={})


def _send(req: PreparedRequest) -> httpx.Response:
    client = _sync_client(req.proxy)
    retried = hops = 0
    while True:
        try:
            response = client.send(_build(client, req), stream=req.stream)
        except httpx.TransportError as exc:
            wait, reason = error_wait(exc, retried, req.retries), type(exc).__name__
            if wait is None:
                raise
        else:
            if (moved := _redirected(req, response, hops)) is not None:
                response.close()
                req, hops = moved, hops + 1
                continue
            wait, reason = answer_wait(response, retried, req.retries), f"HTTP {response.status_code}"
            if wait is None:
                return response
            response.close()
        retried += 1
        _log_retry(req, retried, wait, reason)
        _pause(wait)


async def _asend(req: PreparedRequest) -> httpx.Response:
    client = _async_client(req.proxy)
    retried = hops = 0
    while True:
        try:
            response = await client.send(_build(client, req), stream=req.stream)
        except httpx.TransportError as exc:
            wait, reason = error_wait(exc, retried, req.retries), type(exc).__name__
            if wait is None:
                raise
        else:
            if (moved := _redirected(req, response, hops)) is not None:
                await response.aclose()
                req, hops = moved, hops + 1
                continue
            wait, reason = answer_wait(response, retried, req.retries), f"HTTP {response.status_code}"
            if wait is None:
                return response
            await response.aclose()
        retried += 1
        _log_retry(req, retried, wait, reason)
        await _apause(wait)


def _json_payload(response: httpx.Response, provider: str) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMResponseError(provider, f"{provider} answered with a non-JSON body: {response.text[:200]!r}") from exc
    if not isinstance(payload, dict):
        raise LLMResponseError(provider, f"{provider} answered with a non-object JSON body")
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


# --- streams -------------------------------------------------------------------------------------------------


def finish_reason_of(chunk: Chunk) -> str | None:
    choices = chunk.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reason = choices[0].get("finish_reason")
        return reason if isinstance(reason, str) and reason else None
    return None


class ProviderStream:
    """Sync chunk iterator; ``received_finish_reason`` is what the provider itself reported, never a guess."""

    def __init__(self, response: httpx.Response, decoder: StreamDecoder, req: PreparedRequest) -> None:
        self.received_finish_reason: str | None = None
        self._chunks = self._generate(response, decoder, req)

    def __iter__(self) -> ProviderStream:
        return self

    def __next__(self) -> Chunk:
        return next(self._chunks)

    def close(self) -> None:
        self._chunks.close()

    def _generate(self, response: httpx.Response, decoder: StreamDecoder, req: PreparedRequest) -> Generator[Chunk]:
        try:
            for event, data in iter_stream_events(response, req.framing, req.provider):
                for chunk in decoder.feed(event, data):
                    self.received_finish_reason = finish_reason_of(chunk) or self.received_finish_reason
                    yield chunk
                if decoder.done:
                    break
            for chunk in decoder.finish():
                self.received_finish_reason = finish_reason_of(chunk) or self.received_finish_reason
                yield chunk
        finally:
            response.close()


class AsyncProviderStream:
    """Async twin of :class:`ProviderStream`."""

    def __init__(self, response: httpx.Response, decoder: StreamDecoder, req: PreparedRequest) -> None:
        self.received_finish_reason: str | None = None
        self._chunks = self._generate(response, decoder, req)

    def __aiter__(self) -> AsyncProviderStream:
        return self

    async def __anext__(self) -> Chunk:
        return await self._chunks.__anext__()

    async def aclose(self) -> None:
        await self._chunks.aclose()

    async def _generate(
        self, response: httpx.Response, decoder: StreamDecoder, req: PreparedRequest
    ) -> AsyncGenerator[Chunk]:
        try:
            async for event, data in aiter_stream_events(response, req.framing, req.provider):
                for chunk in decoder.feed(event, data):
                    self.received_finish_reason = finish_reason_of(chunk) or self.received_finish_reason
                    yield chunk
                if decoder.done:
                    break
            for chunk in decoder.finish():
                self.received_finish_reason = finish_reason_of(chunk) or self.received_finish_reason
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
    return ProviderStream(response, decoder, req)


async def aopen_stream(req: PreparedRequest, decoder: StreamDecoder) -> AsyncProviderStream:
    """Async twin of :func:`open_stream`."""
    req = _with_json_headers(req)
    response = await _asend(req)
    try:
        await araise_for_status(response, req.provider)
    except BaseException:
        await response.aclose()
        raise
    return AsyncProviderStream(response, decoder, req)
