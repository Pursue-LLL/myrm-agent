"""``truncate`` keeps the start of a body over the cap and abandons the stream; without it the cap still raises."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from myrm_agent_harness.core.security.http.secure_fetch import ContentTooLargeError, secure_get, secure_request

_PIN = "myrm_agent_harness.core.security.http.secure_fetch.async_pin_url"
_PINNED = ("https://example.com/", {"Host": "example.com"})


class _EndlessStream(httpx.AsyncByteStream):
    """A body that never ends; remembers how much of it was received and whether the client closed it."""

    def __init__(self, chunk: bytes) -> None:
        self._chunk = chunk
        self.received = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            self.received += len(self._chunk)
            yield self._chunk

    async def aclose(self) -> None:
        self.closed = True


async def _get(handler: httpx.MockTransport, **kwargs: object) -> httpx.Response:
    with patch(_PIN, new=AsyncMock(return_value=_PINNED)):
        async with httpx.AsyncClient(transport=handler, follow_redirects=False) as client:
            return await secure_request(client, "GET", "https://example.com", **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_body_over_the_cap_is_cut_at_the_cap_when_truncating() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"y" * 500, request=request))

    response = await _get(transport, max_content_length=100, truncate=True)

    assert response.content == b"y" * 100


@pytest.mark.asyncio
async def test_a_declared_length_over_the_cap_does_not_stop_a_truncating_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "1000"}, content=b"x" * 1000, request=request)

    response = await _get(httpx.MockTransport(handler), max_content_length=100, truncate=True)

    assert response.content == b"x" * 100


@pytest.mark.asyncio
async def test_a_body_within_the_cap_is_returned_whole_when_truncating() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"z" * 60, request=request))

    response = await _get(transport, max_content_length=100, truncate=True)

    assert response.content == b"z" * 60


@pytest.mark.asyncio
async def test_a_cut_is_exact_when_a_chunk_straddles_the_cap() -> None:
    stream = _EndlessStream(b"0123456789")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream, request=request))

    response = await _get(transport, max_content_length=25, truncate=True)

    assert response.content == b"0123456789" * 2 + b"01234"


@pytest.mark.asyncio
async def test_truncating_stops_receiving_an_endless_body_and_closes_the_stream() -> None:
    stream = _EndlessStream(b"a" * 1024)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream, request=request))

    response = await _get(transport, max_content_length=4096, truncate=True)

    assert len(response.content) == 4096
    assert stream.received <= 5 * 1024  # the four chunks it kept and the one that crossed the cap
    assert stream.closed


@pytest.mark.asyncio
async def test_without_truncate_an_oversized_body_still_raises() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"y" * 500, request=request))

    with pytest.raises(ContentTooLargeError):
        await _get(transport, max_content_length=100)


@pytest.mark.asyncio
async def test_secure_get_forwards_truncate() -> None:
    response = httpx.Response(200, content=b"payload", request=httpx.Request("GET", "https://example.com"))

    with patch(
        "myrm_agent_harness.core.security.http.secure_fetch.secure_request", new=AsyncMock(return_value=response)
    ) as forwarded:
        await secure_get("https://example.com", max_content_length=42, truncate=True)

    forwarded.assert_awaited_once()
    assert forwarded.await_args is not None
    assert forwarded.await_args.kwargs["truncate"] is True
