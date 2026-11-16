"""The streams side of the egress guard: SOCKS5 CONNECT parsing, address dialing and the byte relay.

[OUTPUT]
- Connection: a reader and writer pair
- RefusedRequestError: a request that is answered with a SOCKS5 error reply instead of a tunnel
- REPLY_OK, REPLY_FAILURE, REPLY_NOT_ALLOWED, REPLY_HOST_UNREACHABLE: the SOCKS5 reply codes the guard sends
- reply: answer a request
- read_connect_request: negotiate no-authentication SOCKS5 and return the CONNECT destination
- open_first: the first connection that succeeds to a list of addresses
- relay: move bytes both ways until a side fails, goes silent, or both have ended
- close_writer: close a socket now

[POS]
Mechanism with no policy: it never decides what may be connected, it only speaks the protocol, connects to the addresses
it is given and copies bytes. Only the CONNECT command without authentication is served (what Chromium sends for HTTP,
HTTPS and WebSocket traffic); the tunnelled bytes are never parsed.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import struct
from collections.abc import Sequence

Connection = tuple[asyncio.StreamReader, asyncio.StreamWriter]

_STAGGER_S = 0.25  # RFC 8305 connection attempt delay
_MAX_DIAL_ADDRESSES = 8
_CHUNK = 65536

_SOCKS5 = 5
_NO_AUTH = 0
_NO_ACCEPTABLE_METHOD = 0xFF
_CMD_CONNECT = 1
_ATYP_IPV4, _ATYP_DOMAIN, _ATYP_IPV6 = 1, 3, 4
REPLY_OK, REPLY_FAILURE, REPLY_NOT_ALLOWED, REPLY_HOST_UNREACHABLE = 0, 1, 2, 4
_REPLY_COMMAND_UNSUPPORTED, _REPLY_ADDRESS_UNSUPPORTED = 7, 8


class RefusedRequestError(Exception):
    """A request answered with a SOCKS5 error reply instead of a tunnel."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


async def _send(writer: asyncio.StreamWriter, data: bytes) -> None:
    writer.write(data)
    await writer.drain()


async def reply(writer: asyncio.StreamWriter, code: int) -> None:
    """Answer a request; browsers do not use the bound address, so it is always 0.0.0.0:0."""
    await _send(writer, bytes([_SOCKS5, code, 0, _ATYP_IPV4, 0, 0, 0, 0, 0, 0]))


async def read_connect_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> tuple[str, int]:
    """Negotiate no-authentication SOCKS5 and return the destination of the CONNECT request.

    Raises:
        RefusedRequestError: a request the guard does not serve (another command or address type).
        ConnectionError: the peer does not speak SOCKS5 or insists on authentication.
    """
    version, method_count = await reader.readexactly(2)
    methods = await reader.readexactly(method_count)
    if version != _SOCKS5:
        raise ConnectionError("not a SOCKS5 client")
    if _NO_AUTH not in methods:
        await _send(writer, bytes([_SOCKS5, _NO_ACCEPTABLE_METHOD]))
        raise ConnectionError("SOCKS5 client requires authentication")
    await _send(writer, bytes([_SOCKS5, _NO_AUTH]))

    version, command, _reserved, address_type = await reader.readexactly(4)
    if version != _SOCKS5:
        raise ConnectionError("not a SOCKS5 request")
    if address_type == _ATYP_IPV4:
        host = str(ipaddress.IPv4Address(await reader.readexactly(4)))
    elif address_type == _ATYP_IPV6:
        host = str(ipaddress.IPv6Address(await reader.readexactly(16)))
    elif address_type == _ATYP_DOMAIN:
        (length,) = await reader.readexactly(1)
        try:
            host = (await reader.readexactly(length)).decode("ascii")
        except UnicodeDecodeError:
            raise RefusedRequestError(_REPLY_ADDRESS_UNSUPPORTED) from None
        if not host:
            raise RefusedRequestError(_REPLY_ADDRESS_UNSUPPORTED)
    else:
        raise RefusedRequestError(_REPLY_ADDRESS_UNSUPPORTED)
    (port,) = struct.unpack("!H", await reader.readexactly(2))
    if command != _CMD_CONNECT:
        raise RefusedRequestError(_REPLY_COMMAND_UNSUPPORTED)
    return host, port


async def _settle(attempts: set[asyncio.Task[Connection]], connected: list[Connection], timeout: float | None) -> None:
    """Wait until an attempt has connected, every attempt has failed, or ``timeout`` has passed."""
    while attempts and not connected:
        done, _ = await asyncio.wait(attempts, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if not done:
            return
        attempts -= done
        connected.extend(task.result() for task in done if task.exception() is None)


async def _discard(attempts: set[asyncio.Task[Connection]], connected: list[Connection], keep: int) -> None:
    """Cancel the attempts still running and close every connection beyond the first ``keep``: nobody would use them."""
    for task in attempts:
        task.cancel()
    # An attempt that finished while another one won holds a socket too.
    connected.extend(
        outcome for outcome in await asyncio.gather(*attempts, return_exceptions=True) if isinstance(outcome, tuple)
    )
    for _reader, writer in connected[keep:]:
        writer.close()
    del connected[keep:]


async def open_first(addresses: Sequence[str], port: int) -> Connection | None:
    """The first connection that succeeds to one of ``addresses``, or None.

    A new attempt starts every ``_STAGGER_S`` while the earlier ones are still connecting (RFC 8305), so an unreachable
    first address delays a page by a quarter of a second instead of by its whole connect timeout. The caller bounds the
    whole call with a deadline; cancelling it closes every connection that was made.
    """
    attempts: set[asyncio.Task[Connection]] = set()
    connected: list[Connection] = []
    try:
        for address in addresses[:_MAX_DIAL_ADDRESSES]:
            attempts.add(asyncio.ensure_future(asyncio.open_connection(address, port)))
            await _settle(attempts, connected, _STAGGER_S)
            if connected:
                break
        else:
            await _settle(attempts, connected, None)
    except BaseException:  # the caller's deadline passed or the guard is stopping: nothing is handed over
        await _discard(attempts, connected, keep=0)
        raise
    await _discard(attempts, connected, keep=1)
    return connected[0] if connected else None


async def _pipe(source: asyncio.StreamReader, sink: asyncio.StreamWriter, idle_s: float) -> bool:
    """Copy ``source`` into ``sink``: True when ``source`` ended cleanly, False on an error or ``idle_s`` seconds of silence."""
    try:
        while data := await asyncio.wait_for(source.read(_CHUNK), idle_s):
            sink.write(data)
            await asyncio.wait_for(sink.drain(), idle_s)
        if sink.can_write_eof():
            sink.write_eof()
    except (TimeoutError, OSError):
        return False
    return True


async def relay(client: Connection, upstream: Connection, idle_s: float) -> None:
    """Move bytes both ways until one direction fails or goes silent, or both have ended.

    A direction that ends cleanly is forwarded as a half-close and the other one gets to finish; every wait is bounded by
    ``idle_s``, so a peer that stopped reading or vanished cannot hold the tunnel open.
    """
    pending = {
        asyncio.ensure_future(_pipe(client[0], upstream[1], idle_s)),
        asyncio.ensure_future(_pipe(upstream[0], client[1], idle_s)),
    }
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if not all(task.result() for task in done):
                return
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


def close_writer(writer: asyncio.StreamWriter) -> None:
    """Close a socket now. ``abort`` when bytes are still buffered: a peer that stopped reading would hold ``close`` open."""
    with contextlib.suppress(OSError, RuntimeError):  # RuntimeError: the loop is already closed
        if writer.transport.get_write_buffer_size():
            writer.transport.abort()
        else:
            writer.close()
