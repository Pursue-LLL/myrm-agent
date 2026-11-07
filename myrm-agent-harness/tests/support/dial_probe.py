"""A loopback listener that records the Host header of every request, for tests that ask a client which host it dialed.

[INPUT]
- stdlib http.server (POS: in-process HTTP server)

[OUTPUT]
- host_recorder: context manager yielding a ``HostRecorder`` (the listener's port and the Host header received per path)
- Sent: what a client did with one URL (the host the listener saw, or that the client refused the URL)
- Dial: one spelling dialed as its canonical URL and, when its reading as written matters, as written
- misdialed_canonical_urls: the spellings whose canonical URL did not reach the canonical host
- readings_that_differ: how a client read each spelling dialed as written, for those it did not read as the canonical host

[POS]
A client told to connect to 127.0.0.1 whatever name it derives (Chromium's host resolver rules, libcurl's resolve
entries) still sends the name it derived in the Host header, so the header is the observation of which host the client
dialed. Each request uses its own path, so one listener serves a whole table of spellings.
"""

from __future__ import annotations

import ipaddress
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEEPS_THE_TRAILING_DOT = "keeps the trailing dot"
REFUSES_IT = "refuses it"
_SAME_HOST = "same host"
_SENDS_NOTHING = "sends nothing"


@dataclass(slots=True)
class HostRecorder:
    port: int
    hosts: dict[str, str] = field(default_factory=dict)

    def host_sent(self, path: str) -> str | None:
        """The Host header of the request for ``path`` without its port, or None when no such request arrived."""
        sent = self.hosts.get(path)
        return None if sent is None else sent.rpartition(":")[0]


@dataclass(frozen=True, slots=True)
class Sent:
    """What a client did with one URL: the host the listener saw (None when no request arrived) or a refusal."""

    host: str | None = None
    refused: bool = False


@dataclass(frozen=True, slots=True)
class Dial:
    """One spelling, dialed as its canonical URL and, when its reading as written matters, as written."""

    spelling: str
    canonical_host: str
    canonical_url: Sent
    written_url: Sent | None = None


def _same_host(sent: str, canonical: str) -> bool:
    """Whether the host text ``sent`` names the canonical host.

    IPv6 literals are compared as addresses (a client writes ``::ffff:127.0.0.1`` as ``::ffff:7f00:1``); names are
    compared without regard to case, because a client may send the name as it was written.
    """
    if ":" in canonical:
        try:
            return ipaddress.ip_address(sent.strip("[]")) == ipaddress.ip_address(canonical)
        except ValueError:
            return False
    return sent.lower() == canonical


def _reading_as_written(sent: Sent, canonical_host: str) -> str:
    if sent.refused:
        return REFUSES_IT
    if sent.host is None:
        return _SENDS_NOTHING
    if _same_host(sent.host, canonical_host):
        return _SAME_HOST
    if _same_host(sent.host.removesuffix("."), canonical_host):
        return KEEPS_THE_TRAILING_DOT
    return f"sends {sent.host}"


def misdialed_canonical_urls(dials: Sequence[Dial]) -> dict[str, str | None]:
    """Each spelling whose canonical URL did not reach the canonical host, with the host that was sent instead."""
    return {
        dial.spelling: dial.canonical_url.host
        for dial in dials
        if dial.canonical_url.host is None or not _same_host(dial.canonical_url.host, dial.canonical_host)
    }


def readings_that_differ(dials: Sequence[Dial]) -> dict[str, str]:
    """How the client read each spelling dialed as written, for those it did not read as the canonical host."""
    return {
        dial.spelling: reading
        for dial in dials
        if dial.written_url is not None
        and (reading := _reading_as_written(dial.written_url, dial.canonical_host)) != _SAME_HOST
    }


@contextmanager
def host_recorder() -> Iterator[HostRecorder]:
    recorder = HostRecorder(port=0)

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            recorder.hosts[self.path] = self.headers.get("Host", "")
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    recorder.port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield recorder
    finally:
        server.shutdown()
        server.server_close()
