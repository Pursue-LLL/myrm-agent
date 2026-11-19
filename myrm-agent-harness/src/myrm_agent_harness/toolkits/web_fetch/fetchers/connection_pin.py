"""Connection pinning for the L1 tier: libcurl dials only the addresses a fetch vetted.

[INPUT]
- curl_cffi.requests::AsyncSession (POS: the session Scrapling opens for every one-off request; its ``curl_options`` reach libcurl)
- curl_cffi.const::CurlOpt (POS: libcurl option ids; RESOLVE overrides name resolution for one host and port, PROXY switches the environment proxy off)
- scrapling.fetchers::AsyncFetcher (POS: the request path the probe exercises; imported on first use)
- core.security.guards.ssrf::SSRFSecurityError (POS: the terminal verdict a fetch ends with)

[OUTPUT]
- pinned_connection(): async context manager; inside it the curl sessions the current task opens connect to the given addresses when they dial the URL's host
- ensure_connection_pinning(): checks once per process that a pinned request really arrives at the pinned address
- ConnectionPinError: the pin does not take effect, so the fetch is refused

[POS]
L1 connection layer. The SSRF check resolves a name and judges the answer; if libcurl then resolves the name again
for itself, the two answers can differ (DNS rebinding, an answer that changes per query, a resolver that disagrees
with the one that was asked), and the connection goes to an address nobody judged. Here the vetted addresses are given
to libcurl as a ``CURLOPT_RESOLVE`` entry for the host and port, so it connects to those and only those, tries them in
turn when one is down, and still validates the certificate against the host name in the URL (an IP-literal URL cannot).

curl_cffi accepts ``curl_options`` only when a session is created, and Scrapling creates that session itself for every
request. The current task's options therefore sit in a context variable, and ``AsyncSession.__init__`` reads it; a
session created outside ``pinned_connection`` starts as before. The mechanism rests on the installed curl_cffi and
Scrapling, so ``ensure_connection_pinning`` runs one real request before the first pinned fetch and refuses the fetch
when the pin does not arrive, instead of leaving every fetch to the check-then-connect gap. A proxy resolves the host
itself, so a request that goes through one is not pinned.
"""

from __future__ import annotations

import asyncio
import functools
import ipaddress
import logging
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError

if TYPE_CHECKING:
    from curl_cffi.const import CurlOpt

logger = logging.getLogger(__name__)

type _CurlOptions = Mapping[CurlOpt, str | list[str]]

# ``.invalid`` never resolves (RFC 6761), so a request for it can only arrive through the pin.
_PROBE_HOST = "pin-probe.invalid"
_PROBE_TIMEOUT_SECONDS = 3
_INSTALLED_MARKER = "_myrm_connection_pin"

_session_options: ContextVar[_CurlOptions | None] = ContextVar("web_fetch_curl_session_options", default=None)
_probe_passed = False


class ConnectionPinError(SSRFSecurityError):
    """The HTTP client does not connect to the addresses it was pinned to, so a fetch must not rely on the pin."""


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _needs_interface(address: str) -> bool:
    """A link-local IPv6 address only means something together with the interface it was found on."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return parsed.version == 6 and parsed.is_link_local


def _resolve_entry(url: str, addresses: tuple[str, ...]) -> str | None:
    """The libcurl ``host:port:address,address`` entry that limits a connection to ``url``'s host to ``addresses``.

    ``None`` when there is nothing to pin: no addresses, a host that is an IP literal and so dials itself, or an
    address that cannot be written without its interface (only a local-mode origin the user asked for has one).
    """
    parts = urlsplit(url)
    host = parts.hostname
    if not addresses or not host or _is_ip_literal(host) or any(_needs_interface(a) for a in addresses):
        return None
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return f"{host}:{port}:{','.join(addresses)}"


def _install() -> None:
    """Start every curl_cffi session created while ``_session_options`` is set with those libcurl options."""
    from curl_cffi.requests import AsyncSession

    original: Callable[..., None] = AsyncSession.__init__
    if getattr(original, _INSTALLED_MARKER, False):
        return

    @functools.wraps(original)
    def init(self: AsyncSession, *args: object, **kwargs: object) -> None:
        options = _session_options.get()
        if options:
            existing = kwargs.get("curl_options")
            kwargs["curl_options"] = {**existing, **options} if isinstance(existing, dict) else dict(options)
        original(self, *args, **kwargs)

    setattr(init, _INSTALLED_MARKER, True)
    AsyncSession.__init__ = init  # type: ignore[assignment]


@contextmanager
def _session_options_set(options: _CurlOptions) -> Iterator[None]:
    _install()
    token = _session_options.set(options)
    try:
        yield
    finally:
        _session_options.reset(token)


@asynccontextmanager
async def pinned_connection(url: str, addresses: tuple[str, ...]) -> AsyncIterator[None]:
    """Limit the connections the current task makes to ``url``'s host to ``addresses``; nothing changes without any.

    Raises ``ConnectionPinError`` before the first pinned fetch of the process when the pin does not take effect.
    """
    entry = _resolve_entry(url, addresses)
    if entry is None:
        yield
        return

    from curl_cffi.const import CurlOpt

    await ensure_connection_pinning()
    with _session_options_set({CurlOpt.RESOLVE: [entry]}):
        yield


async def ensure_connection_pinning() -> None:
    """Raise ``ConnectionPinError`` unless a pinned request arrives at the address it was pinned to; once per process.

    The request asks for a name that does not resolve and pins it to a listener of this process. It cannot arrive
    unless Scrapling opened a session that carried the pin and libcurl honored it. The environment proxy is switched
    off for the probe, because a proxy would answer for the name instead. Concurrent first calls each run a probe.
    """
    global _probe_passed
    if _probe_passed:
        return

    from curl_cffi.const import CurlOpt
    from scrapling.fetchers import AsyncFetcher  # type: ignore[import-untyped, unused-ignore]

    arrived = asyncio.Event()

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            arrived.set()
            writer.write(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        options: _CurlOptions = {CurlOpt.RESOLVE: [f"{_PROBE_HOST}:{port}:127.0.0.1"], CurlOpt.PROXY: ""}
        with _session_options_set(options):
            await AsyncFetcher.get(
                f"http://{_PROBE_HOST}:{port}/",
                follow_redirects=False,
                retries=1,
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
    except Exception as exc:
        raise ConnectionPinError(_failure_message(f"the probe request failed: {exc}")) from exc
    finally:
        server.close()
        await server.wait_closed()

    if not arrived.is_set():
        raise ConnectionPinError(_failure_message("the probe request was answered by something else"))
    _probe_passed = True
    logger.debug("L1 connection pinning verified")


def _failure_message(reason: str) -> str:
    return (
        f"Connection pinning is not effective ({reason}). The installed scrapling or curl_cffi no longer honors the "
        "resolve override web_fetch relies on, so the HTTP tier refuses to fetch rather than connect to addresses "
        "that were never checked."
    )
