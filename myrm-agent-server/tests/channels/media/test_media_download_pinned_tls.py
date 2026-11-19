"""A pinned HTTPS media download is verified against the host it names, not against the address it was pinned to.

The SSRF guard dials a public host at the address it vetted, so the request URL holds an IP literal. A certificate is
issued for the host name and carries no IP address, so the TLS handshake must still name the host. The listener here is
real TLS on the loopback, and the guard's DNS answer is replaced so that the public host name resolves to it.
"""

from __future__ import annotations

import socket
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from myrm_agent_harness.core.security.guards import ssrf
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult

from app.channels.media import MediaDownloadConfig, MediaDownloader
from tests.support.self_signed_tls import self_signed_certificate

HOST = "cdn.example.org"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class _Media(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG)))
        self.end_headers()
        self.wfile.write(PNG)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output free of per-request lines."""


class _Listener(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: socket.socket | tuple[bytes, socket.socket], client_address: object) -> None:
        """A client that rejects the certificate aborts the handshake: the expected outcome, not an error."""


@contextmanager
def _https_listener(certificate: Path, key: Path) -> Iterator[tuple[int, list[str | None]]]:
    """A loopback HTTPS listener presenting *certificate*; yields its port and the server name of each handshake."""
    server_names: list[str | None] = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    context.sni_callback = lambda _socket, server_name, _context: server_names.append(server_name)
    server = _Listener(("127.0.0.1", 0), _Media)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], server_names
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _client_trusting(certificate: Path) -> httpx.AsyncClient:
    """A client that trusts exactly *certificate* and goes straight to the listener, whatever proxy the machine uses."""
    return httpx.AsyncClient(verify=ssl.create_default_context(cafile=str(certificate)), trust_env=False)


@pytest.fixture(autouse=True)
def public_host_resolves_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def vetted(hostname: str) -> SSRFResult:
        return SSRFResult(safe=True, hostname=hostname, resolved_ips=("127.0.0.1",))

    monkeypatch.setattr(ssrf, "_resolve_and_check_async", vetted)
    monkeypatch.delenv("MYRM_ALLOWED_INTERNAL_HOSTS", raising=False)
    monkeypatch.delenv("MYRM_ENABLE_SSRF_SHIELD", raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("follow_redirects", [True, False])
async def test_pinned_https_download_is_verified_against_the_host_name(tmp_path: Path, follow_redirects: bool) -> None:
    certificate, key = self_signed_certificate(tmp_path, HOST)
    with _https_listener(certificate, key) as (port, server_names):
        async with _client_trusting(certificate) as client:
            result = await MediaDownloader(http_client=client, enable_default_cache=False).download(
                f"https://{HOST}:{port}/logo.png",
                config=MediaDownloadConfig(enable_retry=False, follow_redirects=follow_redirects, timeout_seconds=5),
            )

    assert result.success, result.error
    assert result.data == PNG
    assert server_names
    assert set(server_names) == {HOST}


@pytest.mark.asyncio
async def test_pinned_https_download_rejects_a_certificate_issued_for_another_host(tmp_path: Path) -> None:
    certificate, key = self_signed_certificate(tmp_path, "other.example.org")
    with _https_listener(certificate, key) as (port, _server_names):
        async with _client_trusting(certificate) as client:
            result = await MediaDownloader(http_client=client, enable_default_cache=False).download(
                f"https://{HOST}:{port}/logo.png",
                config=MediaDownloadConfig(enable_retry=False, timeout_seconds=5),
            )

    assert not result.success
    assert "certificate" in str(result.error).lower()
