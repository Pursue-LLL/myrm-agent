"""MYRM_ALLOWED_INTERNAL_HOSTS entries are matched against the canonical host of a URL, so they are kept in that spelling.

A person writes ``0x7f.1`` or ``Büro.local``; the guard compares the host a client dials, ``127.0.0.1`` or
``xn--bro-hoa.local``. Both sides of that comparison must be spelled alike or the listed host would stay closed
(or, with a looser comparison, another host would open).
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError, async_pin_url
from myrm_agent_harness.core.security.http.secure_fetch import parse_allowed_internal_hosts

_ENV = "MYRM_ALLOWED_INTERNAL_HOSTS"


@pytest.mark.parametrize(
    ("raw", "hosts"),
    [
        ("", []),
        (" , ,", []),
        ("localhost, 10.0.0.5 ,, Internal.Corp.", ["localhost", "10.0.0.5", "internal.corp"]),
        ("münchen.local,0x7f.1,ＥＸＡＭＰＬＥ。com", ["xn--mnchen-3ya.local", "127.0.0.1", "example.com"]),
        ("a..b,not a host", ["a..b", "not a host"]),
    ],
)
def test_the_entries_are_listed_in_the_spelling_a_client_dials(
    monkeypatch: pytest.MonkeyPatch, raw: str, hosts: list[str]
) -> None:
    monkeypatch.setenv(_ENV, raw)

    assert parse_allowed_internal_hosts() == hosts


@pytest.mark.asyncio
async def test_a_host_listed_in_any_spelling_opens_the_host_the_client_dials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV, "0x7f.1,Printer.Büro.example")
    allowed = parse_allowed_internal_hosts()
    loop = AsyncMock()
    loop.getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

    with patch("asyncio.get_running_loop", return_value=loop):
        await async_pin_url("http://127.0.0.1:8080/", allowed)
        await async_pin_url("http://2130706433/", allowed)
        await async_pin_url("http://printer.xn--bro-hoa.example/", allowed)
        await async_pin_url("http://PRINTER.büro.example./", allowed)
        for other in ("http://127.0.0.2/", "http://other.example/"):
            with pytest.raises(SSRFSecurityError):
                await async_pin_url(other, allowed)
