"""Each hop of an HTTP-tier fetch is dialed at the addresses its own judgment looked at, and never by name afterwards.

``bounded_get`` is replaced by a recorder that is handed what a real request would be: the URL a hop is requested at
and the addresses it may connect to. Both policies run their real checks on one table of resolver answers. One class
at the end runs the real client against a real listener.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.toolkits.web_fetch.fetchers.bounded_get import FetchedResponse
from myrm_agent_harness.toolkits.web_fetch.fetchers.connection_pin import ConnectionPinError
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from tests.support.tls_loopback import PROXY_VARIABLES

_BOUNDED_GET = "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.bounded_get"
_LOCAL_LOOKUP = "myrm_agent_harness.core.security.redirect_hop_guard.hop_evaluator.resolve_addresses"
_ARTICLE = ("<article><p>" + "x" * 300 + "</p></article>").encode()
_IPV6 = "2606:2800:220:1:248:1893:25c8:1946"
_DNS: dict[str, tuple[str, ...]] = {
    "example.test": ("93.184.216.34",),
    "cdn.example.test": ("151.101.1.69", _IPV6),
    "rebind.example": ("127.0.0.1",),
}

type Hop = tuple[str, tuple[str, ...]]
type Step = FetchedResponse | Exception


def _answer(location: str | None = None) -> FetchedResponse:
    headers = {"Location": location} if location else {"content-type": "text/html"}
    return FetchedResponse(302 if location else 200, headers, "", "utf-8", _ARTICLE)


class _Dialer:
    """Stands in for ``bounded_get``: records what each hop was handed and answers from a script."""

    def __init__(self, *script: Step) -> None:
        self._script = list(script)
        self.hops: list[Hop] = []

    async def __call__(self, url: str, _request: object, addresses: tuple[str, ...] = ()) -> FetchedResponse:
        self.hops.append((url, addresses))
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def dial(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _Dialer]:
    def install(*script: Step) -> _Dialer:
        dialer = _Dialer(*script)
        monkeypatch.setattr(_BOUNDED_GET, dialer)
        return dialer

    return install


@pytest.fixture(autouse=True)
def _resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Names are looked up in ``_DNS``; a name it lacks does not resolve."""

    def getaddrinfo(host: str, *_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host not in _DNS:
            raise socket.gaierror(f"no such host: {host}")
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
            for address in _DNS[host]
        ]

    async def local_lookup(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return tuple(ipaddress.ip_address(address) for address in _DNS.get(host, ()))

    # The cloud policy resolves through the event loop, which calls ``socket.getaddrinfo``; the local policy has a cache.
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(_LOCAL_LOOKUP, local_lookup)


async def _fetch(
    fetcher: HttpFetcher, url: str, *, shield: bool = True, allowed_hosts: list[str] | None = None
) -> FetchResult | None:
    return await fetcher._fetch_with_redirects(
        url, headers={}, cookie_jar=None, enable_ssrf_shield=shield, allowed_hosts=allowed_hosts or []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [HttpFetcher(), HttpFetcher(allow_private_networks=True)], ids=["cloud", "local"])
class TestEveryHopIsDialedAtItsOwnVettedAddresses:
    async def test_a_hop_is_requested_by_name_at_the_addresses_that_were_judged(
        self, fetcher: HttpFetcher, dial: Callable[..., _Dialer]
    ) -> None:
        dialer = dial(_answer())

        assert await _fetch(fetcher, "https://cdn.example.test/a?q=1") is not None

        assert dialer.hops == [("https://cdn.example.test/a?q=1", ("151.101.1.69", _IPV6))]

    async def test_each_redirect_hop_has_its_own_addresses(
        self, fetcher: HttpFetcher, dial: Callable[..., _Dialer]
    ) -> None:
        dialer = dial(_answer("https://cdn.example.test/b"), _answer())

        assert await _fetch(fetcher, "https://example.test/a") is not None

        assert dialer.hops == [
            ("https://example.test/a", ("93.184.216.34",)),
            ("https://cdn.example.test/b", ("151.101.1.69", _IPV6)),
        ]

    async def test_a_failed_connection_is_not_retried_by_name(
        self, fetcher: HttpFetcher, dial: Callable[..., _Dialer]
    ) -> None:
        dialer = dial(OSError("connection refused"), _answer())

        assert await _fetch(fetcher, "https://example.test/a") is None

        assert len(dialer.hops) == 1

    async def test_a_pin_that_does_not_take_effect_ends_the_fetch(
        self, fetcher: HttpFetcher, dial: Callable[..., _Dialer]
    ) -> None:
        dialer = dial(ConnectionPinError("not effective"), _answer())

        with pytest.raises(SSRFSecurityError, match="not effective"):
            await _fetch(fetcher, "https://example.test/a")

        assert len(dialer.hops) == 1


@pytest.mark.asyncio
class TestCloudPolicy:
    async def test_a_redirect_to_a_name_that_resolves_privately_is_never_requested(
        self, dial: Callable[..., _Dialer]
    ) -> None:
        dialer = dial(_answer("https://rebind.example/x"), _answer())

        with pytest.raises(SSRFSecurityError, match="internal network"):
            await _fetch(HttpFetcher(), "https://example.test/a")

        assert dialer.hops == [("https://example.test/a", ("93.184.216.34",))]

    async def test_a_redirect_to_a_name_that_does_not_resolve_is_never_requested(
        self, dial: Callable[..., _Dialer]
    ) -> None:
        dialer = dial(_answer("https://missing.example/x"), _answer())

        with pytest.raises(SSRFSecurityError, match="DNS resolution failed"):
            await _fetch(HttpFetcher(), "https://example.test/a")

        assert len(dialer.hops) == 1

    async def test_an_operator_listed_hop_after_a_pinned_hop_is_not_pinned(self, dial: Callable[..., _Dialer]) -> None:
        dialer = dial(_answer("http://intranet.example/x"), _answer())

        await _fetch(HttpFetcher(), "https://example.test/a", allowed_hosts=["intranet.example"])

        assert dialer.hops == [
            ("https://example.test/a", ("93.184.216.34",)),
            ("http://intranet.example/x", ()),
        ]

    async def test_with_the_shield_off_no_hop_is_pinned(self, dial: Callable[..., _Dialer]) -> None:
        dialer = dial(_answer("https://rebind.example/x"), _answer())

        assert await _fetch(HttpFetcher(), "https://example.test/a", shield=False) is not None

        assert dialer.hops == [("https://example.test/a", ()), ("https://rebind.example/x", ())]


@pytest.mark.asyncio
class TestLocalPolicy:
    async def test_a_requested_name_that_resolves_locally_is_dialed_at_that_address_only(
        self, dial: Callable[..., _Dialer]
    ) -> None:
        """The origin the fetch was aimed at may be private; a later answer for its name may not lead elsewhere."""
        dialer = dial(_answer())

        assert await _fetch(HttpFetcher(allow_private_networks=True), "http://rebind.example:3000/app") is not None

        assert dialer.hops == [("http://rebind.example:3000/app", ("127.0.0.1",))]

    async def test_a_name_with_no_answer_is_left_to_the_client(self, dial: Callable[..., _Dialer]) -> None:
        dialer = dial(_answer())

        await _fetch(HttpFetcher(allow_private_networks=True), "http://devbox.example/app")

        assert dialer.hops == [("http://devbox.example/app", ())]


@pytest.fixture
def loopback_page() -> Iterator[int]:
    """A real HTTP listener on the loopback address that serves an article; yields its port."""

    class Page(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(_ARTICLE)))
            self.end_headers()
            self.wfile.write(_ARTICLE)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:The 'strip_cdata' option")
class TestARealConnection:
    async def test_a_name_no_resolver_knows_is_reached_at_the_address_the_guard_judged(
        self, loopback_page: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the pin can take the client to ``rebind.example``: the guard, the pin and the client work as one."""
        for name in PROXY_VARIABLES:
            monkeypatch.delenv(name, raising=False)

        result = await _fetch(HttpFetcher(allow_private_networks=True), f"http://rebind.example:{loopback_page}/")

        assert result is not None
        assert result.status_code == 200
        assert "x" * 300 in result.html
