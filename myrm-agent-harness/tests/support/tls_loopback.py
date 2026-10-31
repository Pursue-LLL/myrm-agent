"""Real loopback peers and a clean TLS slate for the enterprise network compatibility tests.

``restore_standard_tls`` puts every TLS builder the compatibility policy rebinds back to the library's own, so a test
installs the policy on a known base and the monkeypatch teardown returns whatever the process had. ``https_server``
is a loopback HTTPS listener and ``connect_proxy`` an HTTP proxy that tunnels ``CONNECT`` to it, both on real sockets.
"""

from __future__ import annotations

import inspect
import json
import select
import socket
import socketserver
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp.connector
import pytest
import urllib3.connection
import urllib3.util
import urllib3.util.ssl_ as urllib3_ssl

from tests.support.mcp_testkit.tls_pki import InspectionChain

CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")
PROXY_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")

_COMPLETION = json.dumps(
    {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
).encode()
_RELAY_IDLE_SECONDS = 5


def restore_standard_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standard context builders everywhere the policy rebinds them, and no toggle or CA environment."""
    standard = inspect.unwrap(ssl.create_default_context)
    monkeypatch.setattr(ssl, "create_default_context", standard)
    monkeypatch.setattr(ssl, "_create_default_https_context", standard)

    standard_urllib3 = inspect.unwrap(urllib3_ssl.create_urllib3_context)
    for module in (urllib3_ssl, urllib3.connection, urllib3.util):
        monkeypatch.setattr(module, "create_urllib3_context", standard_urllib3)
    monkeypatch.setattr(urllib3_ssl, "SSLContext", ssl.SSLContext)

    monkeypatch.setattr(aiohttp.connector, "_SSL_CONTEXT_VERIFIED", aiohttp.connector._make_ssl_context(True))
    # ``urlopen`` builds one opener, and so one context, for the life of the process.
    monkeypatch.setattr("urllib.request._opener", None)

    for name in ("MYRM_TLS_STRICT", *CA_ENV_VARS):
        monkeypatch.delenv(name, raising=False)


def isolate_from_system_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loopback traffic goes straight to the listener, whatever proxy the machine running the tests is behind."""
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")


class _Handler(BaseHTTPRequestHandler):
    """Answers every request with a JSON body: an OpenAI chat completion to a POST, ``{}`` to a GET."""

    def _answer(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._answer(b"{}")

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._answer(_COMPLETION)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of per-request lines."""


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: socket.socket | tuple[bytes, socket.socket], client_address: object) -> None:
        """A client that aborts the handshake (a rejected certificate) is the expected outcome, not an error."""


@contextmanager
def https_server(chain: InspectionChain) -> Iterator[str]:
    """A loopback HTTPS listener presenting *chain*; yields its base URL."""
    server = _QuietServer(("127.0.0.1", 0), _Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(chain.server_cert, chain.server_key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _relay(client: socket.socket, upstream: socket.socket) -> None:
    """Copy bytes both ways until either side closes or goes quiet."""
    while True:
        readable, _, _ = select.select([client, upstream], [], [], _RELAY_IDLE_SECONDS)
        if not readable:
            return
        for source in readable:
            data = source.recv(65536)
            if not data:
                return
            (upstream if source is client else client).sendall(data)


class _ConnectHandler(socketserver.BaseRequestHandler):
    server: ConnectProxy

    def handle(self) -> None:
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            head += chunk
        method, target, _version = head.split(b"\r\n", 1)[0].split(b" ", 2)
        if method != b"CONNECT":
            self.request.sendall(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
            return
        host, _, port = target.decode().rpartition(":")
        with socket.create_connection((host, int(port)), timeout=10) as upstream:
            self.server.tunnels.append(target.decode())
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _relay(self.request, upstream)


class ConnectProxy(socketserver.ThreadingTCPServer):
    """A plain-HTTP proxy that tunnels ``CONNECT``; ``tunnels`` lists the targets it was asked to reach."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ConnectHandler)
        self.tunnels: list[str] = []

    def handle_error(self, request: socket.socket | tuple[bytes, socket.socket], client_address: object) -> None:
        """A client that aborts the tunnel (a rejected certificate resets it) is the expected outcome, not an error."""

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


@contextmanager
def connect_proxy() -> Iterator[ConnectProxy]:
    """A ``CONNECT`` proxy on a loopback port."""
    proxy = ConnectProxy()
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        yield proxy
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=5)
