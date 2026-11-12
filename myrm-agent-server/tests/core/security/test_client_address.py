"""Tests for the single client-address source.

The address comes from the ASGI server's own view of the peer; a forwarded header only reaches it through uvicorn's
proxy-header handling, for the peers that handling trusts.
"""

from __future__ import annotations

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.security.client_address import UNKNOWN_CLIENT_IP, client_ip

_TRUSTED_PROXY_NETWORK = "10.0.0.0/8"


def _request(*, client: tuple[str, int] | None, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw_headers, "client": client})


async def _reply_with_client_ip(scope: Scope, receive: Receive, send: Send) -> None:
    await PlainTextResponse(client_ip(Request(scope, receive)))(scope, receive, send)


async def _client_ip_behind_proxy_headers(peer: str, forwarded_for: str | None) -> str:
    """Return the address the app sees when ``peer`` connects through uvicorn's proxy-header middleware."""
    app = ProxyHeadersMiddleware(_reply_with_client_ip, trusted_hosts=_TRUSTED_PROXY_NETWORK)
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 5000)), base_url="http://app") as http:
        return (await http.get("/", headers=headers)).text


def test_client_ip_is_the_peer_address() -> None:
    assert client_ip(_request(client=("198.51.100.7", 4321))) == "198.51.100.7"


@pytest.mark.parametrize("client", [None, ("", 0)])
def test_client_ip_is_unknown_when_the_transport_reports_no_peer(client: tuple[str, int] | None) -> None:
    assert client_ip(_request(client=client)) == UNKNOWN_CLIENT_IP


def test_forged_forwarding_headers_do_not_change_the_client_ip() -> None:
    request = _request(client=("198.51.100.7", 4321), headers={"X-Forwarded-For": "203.0.113.9", "X-Real-IP": "203.0.113.10"})
    assert client_ip(request) == "198.51.100.7"


async def test_a_visitor_cannot_forge_the_address_through_an_unlisted_peer() -> None:
    assert await _client_ip_behind_proxy_headers("198.51.100.7", "203.0.113.9") == "198.51.100.7"


async def test_a_listed_proxy_passes_the_visitor_address_on() -> None:
    assert await _client_ip_behind_proxy_headers("10.0.0.5", "203.0.113.9") == "203.0.113.9"


async def test_a_hop_the_visitor_prepends_does_not_win_behind_a_listed_proxy() -> None:
    # The proxy appends the address it saw; whatever the visitor wrote before it stays to the left.
    assert await _client_ip_behind_proxy_headers("10.0.0.5", "1.1.1.1, 203.0.113.9") == "203.0.113.9"


async def test_a_listed_proxy_without_the_header_leaves_the_peer_address() -> None:
    assert await _client_ip_behind_proxy_headers("10.0.0.5", None) == "10.0.0.5"
