"""A raw SOCKS5 client and a loopback echo server: the egress guard under test without a browser.

[INPUT]
- toolkits.browser.pool::EgressGuard (POS: the proxy under test)

[OUTPUT]
- ECHO_HOST / WAIT_S: the destination name the tests ask for (their resolvers answer loopback for it) and how long a test waits for anything to happen
- Streams: the reader and writer of an open connection
- Upstream / echo_upstream: a loopback echo server that counts the connections that reached it
- started: the port of a started guard, which is stopped when the block ends
- port_of: the port in a guard's proxy settings
- connect: ask the guard for a tunnel; the SOCKS5 reply code and the open streams
- until: wait for a condition
- ends_without_a_reply: the guard closed the connection without answering
- admit_loopback: a resolver that admits loopback for every name

[POS]
Test support for ``test_egress_guard``, ``test_egress_guard_limits`` and ``test_egress_guard_canary``. A raw SOCKS5 client plays the browser
and the echo server plays the destination, so each test can say exactly which connections reached it. The policy that decides what is
admitted is a function the test passes in.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import struct
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from myrm_agent_harness.toolkits.browser.pool import EgressGuard

ECHO_HOST = "echo.test"
WAIT_S = 5.0

type Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]


@dataclass
class Upstream:
    """A loopback echo server; ``connections`` counts what reached it."""

    port: int = 0
    connections: int = 0


@contextlib.asynccontextmanager
async def echo_upstream() -> AsyncIterator[Upstream]:
    upstream = Upstream()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream.connections += 1
        try:
            while data := await reader.read(4096):
                writer.write(data)
                await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    upstream.port = server.sockets[0].getsockname()[1]
    try:
        yield upstream
    finally:
        server.close()


def port_of(settings: dict[str, str]) -> int:
    return int(settings["server"].rsplit(":", 1)[1])


@contextlib.asynccontextmanager
async def started(guard: EgressGuard) -> AsyncIterator[int]:
    """The port of a started guard, which is stopped when the block ends."""
    try:
        yield port_of(await guard.start())
    finally:
        await guard.stop()


def _request(host: str, port: int, *, command: int = 1) -> bytes:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        name = host.encode()
        destination = bytes([3, len(name)]) + name
    else:
        destination = bytes([1 if address.version == 4 else 4]) + address.packed
    return bytes([5, command, 0]) + destination + struct.pack("!H", port)


async def connect(
    guard_port: int, host: str, port: int, *, command: int = 1
) -> tuple[int, asyncio.StreamReader, asyncio.StreamWriter]:
    """Ask the guard for a tunnel; the SOCKS5 reply code and the open streams."""
    reader, writer = await asyncio.open_connection("127.0.0.1", guard_port)
    writer.write(b"\x05\x01\x00")
    assert await reader.readexactly(2) == b"\x05\x00"
    writer.write(_request(host, port, command=command))
    return (await reader.readexactly(10))[1], reader, writer


async def until(condition: Callable[[], bool], timeout_s: float = WAIT_S) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.01)


async def ends_without_a_reply(reader: asyncio.StreamReader) -> bool:
    """The guard dropped the connection: the stream ends (or is reset, as the guard closes with the greeting unread)."""
    try:
        return await asyncio.wait_for(reader.read(), WAIT_S) == b""
    except ConnectionResetError:
        return True


def admit_loopback(_host: str, _port: int) -> tuple[str, ...]:
    return ("127.0.0.1",)
