"""The Telegram client reaches the Bot API through the proxy it is given, for calls and file downloads alike.

A real ``httpx`` client talks to a stand-in proxy over a local socket, so the proxy setting is proven on the
wire: an HTTP proxy receives the request in absolute form, a SOCKS5 proxy receives a CONNECT to the Bot API host.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramClient
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN

_BOT_API = "http://bot-api.test"
_FILE_BYTES = b"file-bytes"

_Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


async def _read_request(reader: asyncio.StreamReader) -> str:
    """Consume one HTTP request (head and body) and return its request line."""
    head = (await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")
    length = next((int(line.split(":", 1)[1]) for line in head if line.lower().startswith("content-length:")), 0)
    if length:
        await reader.readexactly(length)
    return head[0]


async def _answer(writer: asyncio.StreamWriter, request_line: str) -> None:
    """Reply as the Bot API would: bot info for ``getMe``, the file bytes for a download."""
    body = _FILE_BYTES if "/file/" in request_line else json.dumps({"ok": True, "result": {"username": "proxied_bot"}}).encode()
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
    await writer.drain()
    writer.close()


@asynccontextmanager
async def _serving(handler: _Handler) -> AsyncIterator[int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


def _http_proxy(seen: list[str]) -> _Handler:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await _read_request(reader)
        seen.append(line)
        await _answer(writer, line)

    return handle


def _socks5_proxy(seen: list[str]) -> _Handler:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        _, method_count = await reader.readexactly(2)
        await reader.readexactly(method_count)
        writer.write(b"\x05\x00")
        _, _, _, address_type = await reader.readexactly(4)
        if address_type == 3:
            host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
        else:
            host = socket.inet_ntoa(await reader.readexactly(4))
        port = int.from_bytes(await reader.readexactly(2), "big")
        seen.append(f"CONNECT {host}:{port}")
        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await _answer(writer, await _read_request(reader))

    return handle


class TestProxiedClient:
    @pytest.mark.asyncio
    async def test_a_call_goes_through_an_http_proxy(self) -> None:
        seen: list[str] = []
        async with _serving(_http_proxy(seen)) as port:
            client = TelegramClient(FAKE_TELEGRAM_BOT_TOKEN, api_base=_BOT_API, proxy=f"http://127.0.0.1:{port}")
            try:
                me = await client.get_me()
            finally:
                await client.close()

        assert me == {"username": "proxied_bot"}
        assert seen == [f"POST {_BOT_API}/bot{FAKE_TELEGRAM_BOT_TOKEN}/getMe HTTP/1.1"]

    @pytest.mark.asyncio
    async def test_a_file_download_goes_through_an_http_proxy(self) -> None:
        seen: list[str] = []
        async with _serving(_http_proxy(seen)) as port:
            client = TelegramClient(FAKE_TELEGRAM_BOT_TOKEN, api_base=_BOT_API, proxy=f"http://127.0.0.1:{port}")
            try:
                content = await client.download_file("photos/a.jpg")
            finally:
                await client.close()

        assert content == _FILE_BYTES
        assert seen == [f"GET {_BOT_API}/file/bot{FAKE_TELEGRAM_BOT_TOKEN}/photos/a.jpg HTTP/1.1"]

    @pytest.mark.asyncio
    async def test_a_call_goes_through_a_socks5_proxy(self) -> None:
        seen: list[str] = []
        async with _serving(_socks5_proxy(seen)) as port:
            client = TelegramClient(FAKE_TELEGRAM_BOT_TOKEN, api_base=_BOT_API, proxy=f"socks5://127.0.0.1:{port}")
            try:
                me = await client.get_me()
            finally:
                await client.close()

        assert me == {"username": "proxied_bot"}
        assert seen == ["CONNECT bot-api.test:80"]


class TestProxyCredential:
    def test_a_stored_proxy_reaches_the_client(self) -> None:
        channel = TelegramChannel.from_credentials({"token": FAKE_TELEGRAM_BOT_TOKEN, "proxy": "socks5://127.0.0.1:1080"})

        assert channel._client._proxy == "socks5://127.0.0.1:1080"

    @pytest.mark.parametrize("creds", [{}, {"proxy": ""}], ids=["absent", "empty"])
    def test_no_proxy_is_configured_when_none_is_stored(self, creds: dict[str, str]) -> None:
        channel = TelegramChannel.from_credentials({"token": FAKE_TELEGRAM_BOT_TOKEN, **creds})

        assert channel._client._proxy is None

    def test_proxy_is_an_optional_credential_field(self) -> None:
        fields = dict(TelegramChannel.credential_spec.fields)

        assert (fields["proxy"].db_key, fields["proxy"].required) == ("proxy", False)
