"""A small world for the egress guard tests: the public internet, an internal site, and a page that tries to reach it.

[INPUT]
- toolkits.browser.pool.egress_policy::EgressRefusedError, resolve_public_addresses (POS: what a browser may connect to)
- tests.toolkits.browser._fake_dns::url_on (POS: a loopback site's URL under a fake hostname)
- tests.toolkits.browser._redirect_servers::Reply, Site, page, redirect, serve (POS: loopback test servers that record every request)

[OUTPUT]
- PUBLIC_HOST / REBIND_HOST: the name ``table_resolver`` admits (answering loopback, which the tests dial for real, as if
  it were a public address) and the name it refuses (answering an internal address)
- table_resolver: the cloud egress policy with those two names
- ATTACK_PATHS: what the attack page asks of the internal site, by the way a page can start a request
- attack_world: a ``World`` of the public site serving the attack page and the internal site it targets
- launch_options_without_guard: Chromium launch options for the run without the guard (the two names dial loopback, and
  Chromium's own private network checks are off, which would otherwise stop most of the attack page by themselves)
- UdpListener: counts the datagrams sent to a loopback UDP port; ``stun_probe`` is the page script that makes a browser send one

[POS]
Test support for ``test_egress_guard_integration`` and ``test_stealth_fetcher_egress_guard_integration``. The tests run
the same page against a browser with and without the guard: a probe that finds nothing proves nothing unless it can
see something, so the run without the guard has to reach the internal site and the run with it must not.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from myrm_agent_harness.toolkits.browser.pool.egress_policy import EgressRefusedError, resolve_public_addresses
from tests.toolkits.browser._fake_dns import launch_options_dialing_loopback, url_on
from tests.toolkits.browser._redirect_servers import Reply, Site, page, redirect, serve

PUBLIC_HOST = "pub.test"
REBIND_HOST = "rebind.test"
PUBLIC_MARKER = "PUBLIC-PAGE"
INTERNAL_MARKER = "INTERNAL-SECRET"

# Chromium refuses requests from a public page to loopback before connecting (Private Network Access, Local Network
# Access); the run without the guard has to show what a page can reach, so they are off there.
_PRIVATE_NETWORK_CHECKS = (
    "PrivateNetworkAccessSendPreflights",
    "PrivateNetworkAccessRespectPreflightResults",
    "PrivateNetworkAccessForNavigations",
    "BlockInsecurePrivateNetworkRequests",
    "LocalNetworkAccessChecks",
)

# The request each path stands for.
ATTACK_PATHS = {
    "/script.js": "script tag with the literal internal address",
    "/frame": "iframe with the literal internal address",
    "/image": "image with the literal internal address",
    "/fetch": "fetch of the literal internal address",
    "/by-name": "fetch of a name that resolves to the internal address",
    "/after-redirect": "redirect hop of a request to the public site",
    "/beacon": "sendBeacon to the literal internal address",
    "/socket": "WebSocket to the literal internal address",
}

_JAVASCRIPT = "text/javascript"


def table_resolver(host: str, port: int) -> tuple[str, ...]:
    """The cloud egress policy, with ``PUBLIC_HOST`` answering loopback and ``REBIND_HOST`` an internal address."""
    if host == PUBLIC_HOST:
        return ("127.0.0.1",)
    if host == REBIND_HOST:
        raise EgressRefusedError(f"{host} resolves to the non-public address 127.0.0.1")
    return resolve_public_addresses(host, port)


def launch_options_without_guard() -> dict[str, object]:
    """Chromium launch options for a run that has no guard: it dials the two fake names itself and has no private network checks."""
    options = launch_options_dialing_loopback([PUBLIC_HOST, REBIND_HOST])
    args = options["args"]
    assert isinstance(args, list)
    return {**options, "args": [*args, f"--disable-features={','.join(_PRIVATE_NETWORK_CHECKS)}"]}


@dataclass(frozen=True, slots=True)
class World:
    """The public site serves the attack page; every request the internal site receives is a request that got through."""

    public: Site
    internal: Site

    def public_url(self, path: str = "/", *, host: str = PUBLIC_HOST) -> str:
        return url_on(host, self.public, path)

    @property
    def internal_literal(self) -> str:
        """The internal site's base URL by its literal address."""
        return self.internal.base_url


def _attack_page(internal_port: str) -> Reply:
    literal = f"http://127.0.0.1:{internal_port}"
    named = f"http://{REBIND_HOST}:{internal_port}"
    return Reply(
        body=f"""<!DOCTYPE html><html><head></head><body>{PUBLIC_MARKER}
<script src="/own.js"></script>
<script src="{literal}/script.js"></script>
<iframe src="{literal}/frame"></iframe>
<img src="{literal}/image">
<script>
fetch("{literal}/fetch", {{mode: "no-cors"}}).catch(() => {{}});
fetch("{named}/by-name", {{mode: "no-cors"}}).catch(() => {{}});
fetch("/hop", {{mode: "no-cors"}}).catch(() => {{}});
navigator.sendBeacon("{literal}/beacon", "x");
try {{ new WebSocket("ws://127.0.0.1:{internal_port}/socket"); }} catch (error) {{}}
</script></body></html>""".encode()
    )


@contextmanager
def attack_world() -> Iterator[World]:
    """A public site whose page tries every way of reaching the internal site, and the internal site."""
    internal_routes = {
        "/script.js": Reply(body=b"window.internalScriptRan = true", content_type=_JAVASCRIPT),
        "/secret": Reply(body=INTERNAL_MARKER.encode()),
    }
    with serve(internal_routes) as internal:
        port = internal.base_url.rsplit(":", 1)[1]
        public_routes = {
            "/": _attack_page(port),
            "/plain": page(PUBLIC_MARKER),
            "/scripted": page(f'{PUBLIC_MARKER}<script src="/own.js"></script>'),
            "/own.js": Reply(body=b"window.ownScriptRan = true", content_type=_JAVASCRIPT),
            "/hop": redirect(f"http://127.0.0.1:{port}/after-redirect"),
            "/hop-document": redirect(f"http://127.0.0.1:{port}/secret"),
        }
        with serve(public_routes) as public:
            yield World(public=public, internal=internal)


class UdpListener:
    """A loopback UDP port that counts what arrives: what a browser sends outside its proxy shows up here."""

    def __init__(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.settimeout(0.2)
        self.port: int = self._socket.getsockname()[1]
        self.datagrams = 0
        self._open = True
        self._thread = threading.Thread(target=self._count, daemon=True)
        self._thread.start()

    def _count(self) -> None:
        while self._open:
            try:
                self._socket.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                return
            self.datagrams += 1

    def close(self) -> None:
        self._open = False
        self._thread.join(timeout=2)
        self._socket.close()

    def stun_probe(self) -> str:
        """Page script: start an ICE gathering against this port, which sends STUN datagrams when UDP is allowed."""
        return f"""(async () => {{
  const connection = new RTCPeerConnection({{iceServers: [{{urls: "stun:127.0.0.1:{self.port}"}}]}});
  connection.createDataChannel("probe");
  await connection.setLocalDescription(await connection.createOffer());
  await new Promise((resolve) => setTimeout(resolve, 2000));
  connection.close();
}})()"""
