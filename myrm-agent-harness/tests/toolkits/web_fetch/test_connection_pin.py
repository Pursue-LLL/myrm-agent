"""The HTTP tier connects only to the addresses a fetch vetted, whatever else the host name resolves to.

Real curl_cffi, through Scrapling, performs every request here against listeners of this process. A name under
``.invalid`` never resolves (RFC 6761), so a request to one can reach a listener only through the pin.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from curl_cffi.const import CurlOpt
from curl_cffi.requests import AsyncSession, RequestsError
from curl_cffi.requests.exceptions import CertificateVerifyError

from myrm_agent_harness.toolkits.web_fetch.fetchers import bounded_get as bounded_get_module
from myrm_agent_harness.toolkits.web_fetch.fetchers import connection_pin
from myrm_agent_harness.toolkits.web_fetch.fetchers.bounded_get import FetchedResponse, bounded_get
from myrm_agent_harness.toolkits.web_fetch.fetchers.connection_pin import (
    ConnectionPinError,
    ensure_connection_pinning,
    pinned_connection,
)
from tests.support.mcp_testkit.tls_pki import generate_inspection_chain
from tests.support.tls_loopback import PROXY_VARIABLES, https_server

# Scrapling builds its lxml parser with an option lxml now warns about; the project turns warnings into errors.
pytestmark = pytest.mark.filterwarnings("ignore:The 'strip_cdata' option")

_PINNED_NAME = "pin-target.invalid"


@dataclass(slots=True)
class _Listener:
    """A loopback HTTP listener that records every request head it receives and answers with its own label."""

    label: str
    port: int = 0
    heads: list[str] = field(default_factory=list)

    @property
    def body(self) -> bytes:
        return f"<html><body>{self.label}</body></html>".encode()

    @property
    def host_headers(self) -> list[str]:
        lines = (line for head in self.heads for line in head.split("\r\n"))
        return [line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("host:")]


@asynccontextmanager
async def _listen(label: str, *, host: str = "127.0.0.1", port: int = 0) -> AsyncIterator[_Listener]:
    listener = _Listener(label)

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            listener.heads.append((await reader.readuntil(b"\r\n\r\n")).decode("latin-1"))
            head = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {len(listener.body)}\r\n"
            writer.write(f"{head}Connection: close\r\n\r\n".encode() + listener.body)
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(answer, host, port)
    listener.port = server.sockets[0].getsockname()[1]
    try:
        yield listener
    finally:
        server.close()
        await server.wait_closed()


async def _get(url: str, addresses: tuple[str, ...] = ()) -> FetchedResponse:
    return await bounded_get(url, {"timeout": 2, "follow_redirects": False}, addresses)


@pytest.fixture(autouse=True)
def _direct_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """A proxy configured on the machine running the tests would answer for the loopback names instead."""
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.asyncio
class TestPinnedConnection:
    async def test_a_pinned_name_reaches_the_pinned_address_and_keeps_its_name(self) -> None:
        async with _listen("pinned") as site:
            url = f"http://{_PINNED_NAME}:{site.port}/page"

            response = await _get(url, ("127.0.0.1",))

            assert (response.status, response.body) == (200, site.body)
            assert site.host_headers == [f"{_PINNED_NAME}:{site.port}"]

            # Without the pin the name leads nowhere, so the pin is what made the connection.
            with suppress(RequestsError):
                await _get(url)
            assert len(site.heads) == 1

    async def test_the_pin_holds_for_the_host_and_port_it_was_made_for_only(self) -> None:
        async with _listen("pinned") as site:
            async with pinned_connection(f"http://{_PINNED_NAME}:{site.port}/", ("127.0.0.1",)):
                await _get(f"http://{_PINNED_NAME}:{site.port}/")
                with suppress(RequestsError):
                    await _get(f"http://other-target.invalid:{site.port}/")
                with suppress(RequestsError):
                    await _get(f"http://{_PINNED_NAME}:{site.port + 1}/")

            assert site.host_headers == [f"{_PINNED_NAME}:{site.port}"]

    async def test_every_address_is_tried_in_turn(self) -> None:
        """The first address has no listener on this port, so the connection moves on to the next one."""
        async with _listen("second") as site:
            response = await _get(f"http://{_PINNED_NAME}:{site.port}/", ("::1", "127.0.0.1"))

            assert response.body == site.body

    async def test_a_dual_stack_name_is_dialed_at_the_pinned_family_only(self) -> None:
        async with AsyncExitStack() as stack:
            v4 = await stack.enter_async_context(_listen("v4"))
            try:
                v6 = await stack.enter_async_context(_listen("v6", host="::1", port=v4.port))
            except OSError:
                pytest.skip("no IPv6 loopback, or its port is taken")
            url = f"http://localhost:{v4.port}/"

            only_v4 = await _get(url, ("127.0.0.1",))
            only_v6 = await _get(url, ("::1",))

            assert (only_v4.body, only_v6.body) == (v4.body, v6.body)
            assert (len(v4.heads), len(v6.heads)) == (1, 1)

    async def test_concurrent_fetches_keep_their_own_pins(self) -> None:
        async with AsyncExitStack() as stack:
            sites = [await stack.enter_async_context(_listen(f"site-{index}")) for index in range(8)]

            responses = await asyncio.gather(
                *(
                    _get(f"http://target-{index}.invalid:{site.port}/", ("127.0.0.1",))
                    for index, site in enumerate(sites)
                )
            )

            assert [response.body for response in responses] == [site.body for site in sites]
            assert [len(site.heads) for site in sites] == [1] * len(sites)

    async def test_the_certificate_is_checked_against_the_name_in_the_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A client told to dial an address still validates the host the URL names; an IP-literal URL cannot."""
        chain = generate_inspection_chain(tmp_path, server_names=("pin-tls.test",))
        monkeypatch.setenv("CURL_CA_BUNDLE", str(chain.ca_cert))

        with https_server(chain) as base:
            port = base.rsplit(":", 1)[1]

            named = await _get(f"https://pin-tls.test:{port}/", ("127.0.0.1",))
            with pytest.raises(CertificateVerifyError):
                await _get(f"https://127.0.0.1:{port}/")
            with pytest.raises(CertificateVerifyError):
                await _get(f"https://other.test:{port}/", ("127.0.0.1",))

        assert named.status == 200


@pytest.mark.asyncio
class TestSessionsOutsideThePin:
    async def test_a_session_is_pinned_only_inside_the_pinned_connection(self) -> None:
        async with pinned_connection(f"http://{_PINNED_NAME}:8080/", ("127.0.0.1",)):
            inside = AsyncSession(curl_options={CurlOpt.TCP_NODELAY: 1})
        outside = AsyncSession()

        assert inside.curl_options == {CurlOpt.TCP_NODELAY: 1, CurlOpt.RESOLVE: [f"{_PINNED_NAME}:8080:127.0.0.1"]}
        assert outside.curl_options == {}
        await inside.close()
        await outside.close()

    async def test_the_pins_of_concurrent_tasks_do_not_mix(self) -> None:
        barrier = asyncio.Barrier(2)

        async def options_seen(name: str) -> dict[CurlOpt, object]:
            async with pinned_connection(f"http://{name}:8080/", ("127.0.0.1",)):
                await barrier.wait()  # both tasks are inside their own pin before either one opens a session
                session = AsyncSession()
            options = dict(session.curl_options)
            await session.close()
            return options

        first, second = await asyncio.gather(options_seen("a.invalid"), options_seen("b.invalid"))

        assert first == {CurlOpt.RESOLVE: ["a.invalid:8080:127.0.0.1"]}
        assert second == {CurlOpt.RESOLVE: ["b.invalid:8080:127.0.0.1"]}

    async def test_installing_twice_wraps_the_session_once(self) -> None:
        connection_pin._install()
        wrapped = AsyncSession.__init__

        connection_pin._install()

        assert AsyncSession.__init__ is wrapped

    @pytest.mark.parametrize(
        ("url", "addresses"),
        [("http://127.0.0.1:8080/", ("127.0.0.1",)), ("http://[::1]/", ("::1",)), ("http://example.test/", ())],
        ids=["ipv4-literal", "ipv6-literal", "name-without-addresses"],
    )
    async def test_nothing_is_pinned_when_there_is_nothing_to_pin(self, url: str, addresses: tuple[str, ...]) -> None:
        async with pinned_connection(url, addresses):
            session = AsyncSession()

        assert session.curl_options == {}
        await session.close()


class TestResolveEntry:
    @pytest.mark.parametrize(
        ("url", "addresses", "entry"),
        [
            ("https://example.test/a?q=1", ("93.184.216.34",), "example.test:443:93.184.216.34"),
            ("http://example.test/", ("93.184.216.34",), "example.test:80:93.184.216.34"),
            (
                "http://example.test:8080/",
                ("93.184.216.34", "2606:2800:220:1::1"),
                "example.test:8080:93.184.216.34,2606:2800:220:1::1",
            ),
            ("https://user:pw@Example.test./x", ("93.184.216.34",), "example.test.:443:93.184.216.34"),
        ],
    )
    def test_the_entry_names_the_host_the_port_and_every_address(
        self, url: str, addresses: tuple[str, ...], entry: str
    ) -> None:
        assert connection_pin._resolve_entry(url, addresses) == entry

    @pytest.mark.parametrize(
        ("url", "addresses"),
        [
            ("https://example.test/", ()),
            ("https://93.184.216.34/", ("93.184.216.34",)),
            ("https://[2606:2800:220:1::1]/", ("2606:2800:220:1::1",)),
            ("https://example.test/", ("fe80::1",)),
            ("https://example.test/", ("93.184.216.34", "fe80::1")),
        ],
        ids=["no-address", "ipv4-literal", "ipv6-literal", "link-local-v6", "link-local-v6-among-others"],
    )
    def test_there_is_no_entry_when_there_is_nothing_to_pin_or_it_cannot_be_written(
        self, url: str, addresses: tuple[str, ...]
    ) -> None:
        assert connection_pin._resolve_entry(url, addresses) is None


@contextmanager
def _options_dropped(_options: object) -> Iterator[None]:
    """A Scrapling that no longer opens its sessions the way the pin reaches them."""
    yield


@pytest.mark.asyncio
class TestProbe:
    @pytest.fixture(autouse=True)
    def _unverified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(connection_pin, "_probe_passed", False)

    async def test_the_installed_clients_honor_the_pin(self) -> None:
        await ensure_connection_pinning()

        assert connection_pin._probe_passed is True

    async def test_a_passed_probe_is_not_repeated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        await ensure_connection_pinning()
        monkeypatch.setattr(asyncio, "start_server", AsyncMock(side_effect=AssertionError("probed again")))

        await ensure_connection_pinning()

    async def test_an_environment_proxy_does_not_fool_or_fail_the_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in PROXY_VARIABLES:
            monkeypatch.setenv(name, "http://127.0.0.1:1")

        await ensure_connection_pinning()

        assert connection_pin._probe_passed is True

    async def test_a_pin_that_does_not_arrive_fails_the_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(connection_pin, "_session_options_set", _options_dropped)

        with pytest.raises(ConnectionPinError, match="Connection pinning is not effective"):
            await ensure_connection_pinning()

        assert connection_pin._probe_passed is False

    async def test_a_fetch_is_refused_while_the_pin_does_not_arrive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(connection_pin, "_session_options_set", _options_dropped)

        async with _listen("pinned") as site:
            with pytest.raises(ConnectionPinError):
                await _get(f"http://{_PINNED_NAME}:{site.port}/", ("127.0.0.1",))

            assert site.heads == []


@pytest.mark.asyncio
async def test_a_request_through_a_proxy_is_not_pinned(
    install_fake_scrapling: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A proxy resolves the host itself, so the addresses of the fetch's own lookup mean nothing to that request."""
    pinned = MagicMock()

    @asynccontextmanager
    async def record(url: str, addresses: tuple[str, ...]) -> AsyncIterator[None]:
        pinned(url, addresses)
        yield

    monkeypatch.setattr(bounded_get_module, "pinned_connection", record)
    response = MagicMock(status=200, headers={}, url="http://example.test/", encoding="utf-8", body=b"")
    install_fake_scrapling.return_value = response

    await bounded_get("http://example.test/", {"proxy": "http://proxy.test:8080"}, ("93.184.216.34",))
    await bounded_get("http://example.test/", {}, ("93.184.216.34",))

    assert [call.args for call in pinned.call_args_list] == [
        ("http://example.test/", ()),
        ("http://example.test/", ("93.184.216.34",)),
    ]
