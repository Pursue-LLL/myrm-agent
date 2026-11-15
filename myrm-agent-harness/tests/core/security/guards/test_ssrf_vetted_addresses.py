"""``async_vetted_addresses``: the addresses a client may connect to when it keeps the host name in the URL.

Every address a host resolves to must be public, so a single private answer blocks the host; the addresses that
pass are what the caller pins the connection to. The resolver is answered from a table, so no test touches the network.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFResult, SSRFSecurityError, async_vetted_addresses
from myrm_agent_harness.core.security.guards.url_allowlist import URLAllowlistGuard

_SSRF = "myrm_agent_harness.core.security.guards.ssrf"


@contextmanager
def _resolver_answers(*addresses: str) -> Iterator[AsyncMock]:
    """The event loop's resolver answers ``addresses``; yields its ``getaddrinfo`` so a test can see the lookup."""
    loop = MagicMock()
    loop.getaddrinfo = AsyncMock(
        return_value=[
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
            for address in addresses
        ]
    )
    with patch("asyncio.get_running_loop", return_value=loop):
        yield loop.getaddrinfo


@pytest.mark.asyncio
class TestVettedAddresses:
    async def test_every_public_address_is_returned_in_the_resolvers_order(self) -> None:
        with _resolver_answers("93.184.216.34", "2606:2800:220:1::1") as lookup:
            addresses = await async_vetted_addresses("https://example.test/a?q=1")

        assert addresses == ("93.184.216.34", "2606:2800:220:1::1")
        lookup.assert_awaited_once_with("example.test", None, proto=socket.IPPROTO_TCP)

    async def test_an_address_the_resolver_repeats_is_listed_once(self) -> None:
        with _resolver_answers("8.8.8.8", "8.8.4.4", "8.8.8.8"):
            assert await async_vetted_addresses("https://example.test/") == ("8.8.8.8", "8.8.4.4")

    @pytest.mark.parametrize("private", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "::1", "fd00::1"])
    async def test_one_private_address_among_public_ones_blocks_the_host(self, private: str) -> None:
        with (
            _resolver_answers("93.184.216.34", private),
            patch(f"{_SSRF}.record_decision") as audit,
            pytest.raises(SSRFSecurityError, match="Access to internal network is blocked"),
        ):
            await async_vetted_addresses("https://example.test/")

        assert audit.call_args.args[1] == "SSRF_BLOCKED"

    async def test_a_host_the_operator_listed_is_not_resolved_and_has_no_addresses(self) -> None:
        with _resolver_answers("10.0.0.5") as lookup:
            addresses = await async_vetted_addresses("http://nas.example/api", allowed_internal_hosts=["nas.example"])

        assert addresses == ()
        lookup.assert_not_awaited()

    async def test_a_public_literal_is_its_own_address_without_a_lookup(self) -> None:
        with _resolver_answers("10.0.0.5") as lookup:
            assert await async_vetted_addresses("http://8.8.8.8:8080/") == ("8.8.8.8",)

        lookup.assert_not_awaited()

    @pytest.mark.parametrize("literal", ["http://10.0.0.5/", "http://[::1]/", "http://169.254.169.254/"])
    async def test_a_private_literal_is_blocked(self, literal: str) -> None:
        with pytest.raises(SSRFSecurityError):
            await async_vetted_addresses(literal)

    async def test_a_name_that_does_not_resolve_is_blocked(self) -> None:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(side_effect=socket.gaierror("no such host"))

        with (
            patch("asyncio.get_running_loop", return_value=loop),
            pytest.raises(SSRFSecurityError, match="DNS resolution failed"),
        ):
            await async_vetted_addresses("https://nohost.example/")

    async def test_an_answer_with_no_address_is_blocked(self) -> None:
        async def empty(hostname: str) -> SSRFResult:
            return SSRFResult(safe=True, hostname=hostname, resolved_ips=())

        with (
            patch(f"{_SSRF}._resolve_and_check_async", empty),
            pytest.raises(SSRFSecurityError, match="DNS resolution failed"),
        ):
            await async_vetted_addresses("https://nohost.example/")

    async def test_the_skill_domain_allowlist_applies_before_any_lookup(self) -> None:
        with (
            _resolver_answers("93.184.216.34") as lookup,
            URLAllowlistGuard.apply(["api.github.com"]),
            pytest.raises(SSRFSecurityError, match=r"Access to evil\.test is blocked"),
        ):
            await async_vetted_addresses("https://evil.test/")

        lookup.assert_not_awaited()

    @pytest.mark.parametrize("url", ["ftp://example.test/", "not-a-url", "file:///etc/passwd"])
    async def test_an_unusable_url_is_refused(self, url: str) -> None:
        with pytest.raises(SSRFSecurityError):
            await async_vetted_addresses(url)
