"""A loopback HTTP proxy that answers each proxied POST itself, for tests that ask which address a client sent through it.

[INPUT]
- stdlib http.server (POS: in-process HTTP server)

[OUTPUT]
- ForwardProxy: the listener; ``url`` is how a client names it, ``targets`` the address of every request it received
- forward_proxy: context manager running one on a loopback port

[POS]
A client told to use a proxy puts the whole target address (``POST http://host/path``) in the request line instead of
connecting to the host, so the request line shows both that the proxy was used and where the client wanted to go. The
target host may exist nowhere: an answer that arrives then came from the proxy, not from the host.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    server: ForwardProxy

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.targets.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.server.answer)))
        self.end_headers()
        self.wfile.write(self.server.answer)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of the server's access log."""


class ForwardProxy(ThreadingHTTPServer):
    """Answers every proxied POST with ``answer`` (a JSON document) and lists the addresses it was asked for."""

    daemon_threads = True

    def __init__(self, answer: bytes) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.answer = answer
        self.targets: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


@contextmanager
def forward_proxy(answer: bytes = b'{"ok": true}') -> Iterator[ForwardProxy]:
    """A forwarding proxy on a loopback port that answers with ``answer``."""
    proxy = ForwardProxy(answer)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        yield proxy
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=5)
