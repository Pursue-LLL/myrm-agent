"""A failed delivery lands in the category a person would name for it, for the errors the real code raises.

[INPUT]
- toolkits.cron.delivery::WebhookDelivery (POS: built-in webhook ResultDelivery; refuses an address before it dials)
- toolkits.cron.engine.connector_health::classify_connector_error (POS: delivery failure taxonomy)
- httpx (POS: the client whose transport errors are raised against a loopback listener)

[OUTPUT]
- every address the SSRF guard refuses reaches the classifier as ADDRESS_REJECTED
- a connection that is dropped, cut mid-body or reset is NETWORK_UNREACHABLE, and a listener that answers with
  something other than HTTP is PAYLOAD_CONTRACT

[POS]
The text table in test_cron_connector_health.py pins the classifier against fixed strings. This pins it against the
exceptions the delivery paths really raise, whose text comes from the libraries underneath.
"""

from __future__ import annotations

import asyncio
import socket
import struct
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
import pytest

from myrm_agent_harness.toolkits.cron.delivery import WebhookDelivery
from myrm_agent_harness.toolkits.cron.engine.connector_health import ConnectorErrorCategory, classify_connector_error
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobType,
    Schedule,
    ScheduleKind,
)

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


def _job(url: str) -> CronJob:
    return CronJob(
        id="j1",
        name="report",
        job_type=JobType.SHELL,
        command="echo hi",
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000),
        delivery=DeliveryConfig(channel="webhook", target=url, secret="s3cret"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# Every one of these is refused before a connection is attempted, so no name is resolved and nothing is dialed.
_REFUSED_ADDRESSES = {
    "loopback-name": "http://localhost/hook",
    "private-ip": "http://192.168.1.20/hook",
    "link-local": "http://169.254.169.254/latest",
    "no-scheme": "hooks.example.com/hook",
    "ftp-scheme": "ftp://hooks.example.com/hook",
    "empty-host": "https:///hook",
    "bad-port": "https://hooks.example.com:abc/hook",
    "percent-encoded-host": "https://127%2e0%2e0%2e1/hook",
    "internal-suffix": "https://printer.local/hook",
    "control-character": "https://hooks.example.com/a\tb",
}


@pytest.mark.parametrize("url", _REFUSED_ADDRESSES.values(), ids=_REFUSED_ADDRESSES.keys())
async def test_an_address_the_guard_refuses_is_classed_address_rejected(url: str) -> None:
    with pytest.raises(ValueError) as refused:
        await WebhookDelivery(max_retries=0).deliver(_job(url), JobResult(success=True, output="report"))

    assert classify_connector_error(refused.value)[0] == ConnectorErrorCategory.ADDRESS_REJECTED


async def _hang_up(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.close()


async def _cut_the_body(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\npartial")
    await writer.drain()
    writer.close()


async def _reset(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.readuntil(b"\r\n\r\n")
    # A zero linger time turns the close into a reset instead of an orderly shutdown.
    writer.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    writer.close()


async def _speak_something_else(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"not http at all\r\n\r\n")
    await writer.drain()
    writer.close()


async def _failure_against(handler: Handler) -> httpx.HTTPError:
    """The error an HTTP client raises when the listener behind ``handler`` receives its request."""
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            with pytest.raises(httpx.HTTPError) as failure:
                await client.post(f"http://127.0.0.1:{port}/hook", content=b"{}")
        return failure.value
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize(
    ("handler", "category"),
    [
        (_hang_up, ConnectorErrorCategory.NETWORK_UNREACHABLE),
        (_cut_the_body, ConnectorErrorCategory.NETWORK_UNREACHABLE),
        (_reset, ConnectorErrorCategory.NETWORK_UNREACHABLE),
        (_speak_something_else, ConnectorErrorCategory.PAYLOAD_CONTRACT),
    ],
    ids=["hang-up", "cut-the-body", "reset", "not-http"],
)
async def test_what_a_listener_does_to_the_request_decides_the_category(
    handler: Handler, category: ConnectorErrorCategory
) -> None:
    failure = await _failure_against(handler)

    assert classify_connector_error(failure)[0] == category
