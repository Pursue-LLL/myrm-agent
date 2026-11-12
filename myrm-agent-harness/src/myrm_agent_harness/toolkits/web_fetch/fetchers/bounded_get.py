"""A GET through Scrapling whose body is held to a size bound while it is received.

[INPUT]
- toolkits.web_fetch.processing.binary_router::MAX_BINARY_SIZE (POS: the largest file body the router parses)
- scrapling.fetchers::AsyncFetcher (POS: curl_cffi request with TLS impersonation; imported on first use)
- curl_cffi.curl::CURL_WRITEFUNC_ERROR (POS: the write-callback result that ends a transfer)
- curl_cffi.requests::RequestsError (POS: what a transfer ended by the callback raises, carrying its response)

[OUTPUT]
- MAX_TRANSFER_BYTES: the most decoded body bytes a fetch holds without being over the bound
- FetchedResponse: status, headers, final URL, encoding hint and the kept body of one GET
- bounded_get: AsyncFetcher.get that keeps at most MAX_TRANSFER_BYTES + 1 body bytes and ends the transfer there

[POS]
L1 transfer bound. Scrapling buffers a whole response and parses it as a document before any size check can run, so
a hostile or mistaken URL (a gzip bomb, a multi-gigabyte file) costs memory and event-loop time in proportion to what
the server sends. Here libcurl hands each decoded chunk to a sink that keeps the first MAX_TRANSFER_BYTES + 1 bytes
and ends the transfer, so the cost stops at that size.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.web_fetch.processing.binary_router import MAX_BINARY_SIZE

if TYPE_CHECKING:
    from scrapling.engines._browsers._types import GetRequestParams  # type: ignore[import-untyped, unused-ignore]

# A file is the payload with the largest ceiling, so a transfer is bounded by the size the binary router parses. One
# byte more is kept so that a body over the bound can be told from a body exactly at it.
MAX_TRANSFER_BYTES = MAX_BINARY_SIZE
_KEPT_BYTES = MAX_TRANSFER_BYTES + 1


@dataclass(frozen=True, slots=True)
class FetchedResponse:
    """What one GET returned: the response line and headers, and the body up to the transfer bound."""

    status: int
    headers: dict[str, str]
    url: str
    encoding: str | None
    body: bytes


class _BodySink:
    """libcurl write callback: keeps the first ``_KEPT_BYTES`` bytes and ends the transfer once they are full."""

    __slots__ = ("_abort", "_buffer", "_size", "capped")

    def __init__(self, abort: int) -> None:
        self._abort = abort
        self._buffer = io.BytesIO()
        self._size = 0
        self.capped = False

    def __call__(self, chunk: bytes) -> int:
        self._size += self._buffer.write(chunk[: _KEPT_BYTES - self._size])
        if self._size < _KEPT_BYTES:
            return len(chunk)
        self.capped = True
        return self._abort

    @property
    def body(self) -> bytes:
        # ``getvalue`` shares the buffer instead of copying it, so a full body is held once; ``bytes(bytearray)``
        # would hold it twice at this point, and every concurrent capped transfer pays that.
        return self._buffer.getvalue()


async def bounded_get(url: str, request: GetRequestParams) -> FetchedResponse:
    """GET ``url`` with Scrapling's request parameters, keeping at most ``MAX_TRANSFER_BYTES + 1`` body bytes.

    Scrapling forwards the ``content_callback`` argument to curl_cffi unchanged. The request is attempted once
    (``retries=1``): a transfer the sink ended on purpose must not be repeated.
    """
    # Imported here, like Scrapling, so that the module loads without the ``web`` extra installed.
    from curl_cffi.curl import CURL_WRITEFUNC_ERROR
    from curl_cffi.requests import RequestsError
    from scrapling.fetchers import AsyncFetcher  # type: ignore[import-untyped, unused-ignore]

    sink = _BodySink(CURL_WRITEFUNC_ERROR)
    single_attempt: GetRequestParams = {**request, "retries": 1}
    try:
        response = await AsyncFetcher.get(url, content_callback=sink, **single_attempt)  # type: ignore[call-arg]
    except RequestsError as exc:
        # The sink ending the transfer surfaces as a write error that carries the response whose status and headers
        # had already arrived. Any other failure is the caller's to handle. Scrapling logs the write error once.
        interrupted = exc.response
        if not sink.capped or interrupted is None:
            raise
        return FetchedResponse(
            interrupted.status_code, dict(interrupted.headers), interrupted.url, interrupted.encoding, sink.body
        )
    return FetchedResponse(response.status, dict(response.headers), response.url, response.encoding, sink.body)
