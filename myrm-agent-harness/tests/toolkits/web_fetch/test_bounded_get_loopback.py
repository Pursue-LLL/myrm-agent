"""The real Scrapling and curl_cffi end a transfer at the bound, against a loopback origin.

The origin declares bodies far beyond the bound and notes how much of each it sent, so a transfer that ended early
shows as a short send. Library behaviour this relies on: Scrapling forwards the write callback to curl_cffi, libcurl
hands that callback decoded bytes, and the write error it raises on the abort carries the response already received.
"""

from __future__ import annotations

import asyncio
import zlib
from collections.abc import AsyncIterator, Iterator
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.bounded_get import MAX_TRANSFER_BYTES, bounded_get
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import MAX_HTML_BODY_BYTES, HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.processing.binary_router import route_binary_content
from myrm_agent_harness.utils.content_sniff import PayloadKind

pytestmark = pytest.mark.integration

curl_requests = pytest.importorskip("curl_cffi.requests")

_MIB = 1 << 20
_REQUEST = {"timeout": 10, "follow_redirects": False}
_HTML_BLOCK = (b"<p>" + b"x" * 1000 + b"</p>\n") * 64
_FILE_BLOCK = b"0123456789" * 6400
_SMALL_PAGE = b"<html><body><article><p>" + b"hello world " * 40 + b"</p></article></body></html>"


def _blocks(content_type: str) -> Iterator[bytes]:
    if "pdf" in content_type:
        yield b"%PDF-1.4\n"
        while True:
            yield _FILE_BLOCK
    while True:
        yield _HTML_BLOCK


class _Origin:
    """Loopback HTTP/1.1 origin; the query of a request describes the response to send.

    ``size`` is the declared length, ``send`` how much is actually written (all of it by default), ``type`` the content
    type, ``status`` the status line, ``gzip=1`` a gzip body whose decoded length is ``size``, and ``stall=1`` keeps the
    connection open after the last byte until the client goes away.
    """

    def __init__(self) -> None:
        self.sent: dict[str, int] = {}
        self._server: asyncio.Server | None = None
        self._port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self._port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        self._server.close_clients()
        await self._server.wait_closed()

    def url(self, target: str) -> str:
        return f"http://127.0.0.1:{self._port}{target}"

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = (await reader.readuntil(b"\r\n\r\n")).split(b"\r\n", 1)[0].decode()
            target = request.split(" ")[1]
            parsed = urlparse(target)
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if parsed.path == "/small":
                writer.write(self._head(200, {"Content-Type": "text/html; charset=utf-8"}, len(_SMALL_PAGE)))
                writer.write(_SMALL_PAGE)
                await writer.drain()
            else:
                await self._stream(target, parsed.path, query, reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _stream(
        self, target: str, path: str, query: dict[str, str], reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        size = int(query["size"])
        send = int(query.get("send", size))
        content_type = query.get("type", "text/html; charset=utf-8")
        headers = {"Content-Type": content_type, "X-Probe": "kept"}
        compressor = zlib.compressobj(1, zlib.DEFLATED, 31) if query.get("gzip") == "1" else None
        if compressor is not None:
            headers["Content-Encoding"] = "gzip"
        if path == "/redirect":
            headers["Location"] = "/small"
        status = 302 if path == "/redirect" else int(query.get("status", 200))
        writer.write(self._head(status, headers, None if compressor else size))
        sent = 0
        self.sent[target] = 0
        blocks = _blocks(content_type)
        try:
            while sent < send:
                piece = next(blocks)[: send - sent]
                writer.write(compressor.compress(piece) if compressor else piece)
                sent += len(piece)
                self.sent[target] = sent
                await writer.drain()
            if compressor:
                writer.write(compressor.flush())
            if query.get("stall") == "1":
                await reader.read()
        except ConnectionError:
            pass

    @staticmethod
    def _head(status: int, headers: dict[str, str], length: int | None) -> bytes:
        lines = [f"HTTP/1.1 {status} {HTTPStatus(status).phrase}", "Connection: close"]
        if length is not None:
            lines.append(f"Content-Length: {length}")
        lines.extend(f"{name}: {value}" for name, value in headers.items())
        return ("\r\n".join(lines) + "\r\n\r\n").encode()


@pytest.fixture
async def origin() -> AsyncIterator[_Origin]:
    server = _Origin()
    await server.start()
    yield server
    await server.stop()


def _fetcher(timeout: int = 10) -> HttpFetcher:
    return HttpFetcher(allow_private_networks=True, timeout=timeout)


async def test_page_over_the_bound_is_cut_and_the_origin_is_not_read_to_the_end(origin: _Origin) -> None:
    target = f"/page?size={200 * _MIB}"

    result = await _fetcher().fetch(origin.url(target))

    assert result is not None
    assert result.source_truncated
    assert len(result.html) == MAX_HTML_BODY_BYTES
    assert origin.sent[target] < 100 * _MIB


async def test_gzip_body_is_bounded_by_its_decoded_size(origin: _Origin) -> None:
    fetched = await bounded_get(origin.url(f"/page?size={80 * _MIB}&gzip=1"), _REQUEST)

    assert fetched.status == 200
    assert len(fetched.body) == MAX_TRANSFER_BYTES + 1


async def test_file_over_the_bound_arrives_one_byte_over_and_the_router_drops_it(origin: _Origin) -> None:
    result = await _fetcher().fetch(origin.url(f"/file?size={64 * _MIB}&type=application/pdf"))

    assert result is not None
    assert result.kind is PayloadKind.BINARY
    assert result.raw_body is not None
    assert len(result.raw_body) == MAX_TRANSFER_BYTES + 1
    assert await route_binary_content(result.raw_body, result.headers, result.url) is None


async def test_page_that_stalls_after_the_bound_is_not_waited_for(origin: _Origin) -> None:
    result = await _fetcher(timeout=5).fetch(origin.url(f"/page?size={2048 * _MIB}&send={24 * _MIB}&stall=1"))

    assert result is not None
    assert result.source_truncated


async def test_redirect_with_a_huge_body_is_still_followed(origin: _Origin) -> None:
    target = f"/redirect?size={64 * _MIB}"

    result = await _fetcher().fetch(origin.url(target))

    assert result is not None
    assert result.status_code == 200
    assert result.url.endswith("/small")
    assert "hello world" in result.html
    assert origin.sent[target] < 64 * _MIB


async def test_status_and_headers_survive_the_abort(origin: _Origin) -> None:
    fetched = await bounded_get(origin.url(f"/page?size={64 * _MIB}&status=404"), _REQUEST)

    assert fetched.status == 404
    assert fetched.headers["x-probe"] == "kept"
    assert len(fetched.body) == MAX_TRANSFER_BYTES + 1


@pytest.mark.parametrize("size", [MAX_TRANSFER_BYTES, MAX_TRANSFER_BYTES + 1])
async def test_a_body_at_the_bound_is_told_from_one_byte_over(origin: _Origin, size: int) -> None:
    fetched = await bounded_get(origin.url(f"/page?size={size}"), _REQUEST)

    assert len(fetched.body) == size


async def test_transfer_that_breaks_before_the_bound_is_raised(origin: _Origin) -> None:
    with pytest.raises(curl_requests.RequestsError):
        await bounded_get(origin.url(f"/page?size={8 * _MIB}&send={_MIB}"), _REQUEST)


async def test_ordinary_page_passes_through_unchanged(origin: _Origin) -> None:
    fetched = await bounded_get(origin.url("/small"), _REQUEST)

    assert (fetched.status, fetched.body, fetched.encoding) == (200, _SMALL_PAGE, "utf-8")
