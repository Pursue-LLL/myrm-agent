"""S3 backup client and the enterprise network compatibility setting.

[INPUT]
app.services.memory.backup.remote_sync.storage::S3BackupStrategy/S3BackupConfig

[OUTPUT]
That the S3 client takes its TLS context from ``ssl.create_default_context`` while the setting is on, keeps aiobotocore's
own trust while it is off, and still rejects a peer the context does not trust while it is on.

[POS]
The real strategy and the real ``aioboto3`` against a loopback HTTPS listener with a self-signed certificate. What the
policy trusts is covered by the harness tests; here ``ssl.create_default_context`` is replaced for the length of a test by
a stand-in context, so the test installs no process-wide TLS state.
"""

from __future__ import annotations

import ssl
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.services.memory.backup.remote_sync.storage import S3BackupConfig, S3BackupStrategy
from tests.support.self_signed_tls import self_signed_certificate

_AMBIENT_NETWORK_VARIABLES = (
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
    "AWS_CA_BUNDLE",
)


class _Handler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request: object, client_address: object) -> None:
        """A client that rejects the certificate abandons the handshake; that is the case under test, not an error."""


@pytest.fixture
def listener(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, Path]]:
    """A loopback HTTPS listener that answers every ``HEAD``; yields its URL and its self-signed certificate."""
    for name in _AMBIENT_NETWORK_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("AWS_MAX_ATTEMPTS", "1")  # a rejected certificate would otherwise be retried with backoff

    certificate_file, key_file = self_signed_certificate(tmp_path)
    server = _QuietServer(("127.0.0.1", 0), _Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_file, key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}", certificate_file
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _trusting(certificate: Path) -> Callable[..., ssl.SSLContext]:
    """A stand-in for the policy's context builder: verification on, trusting exactly *certificate*."""

    def create_default_context(*args: object, **options: object) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(certificate))
        return context

    return create_default_context


def _strategy(endpoint: str) -> S3BackupStrategy:
    return S3BackupStrategy(
        S3BackupConfig(endpoint=endpoint, region="eu-west-1", bucket="vault", access_key_id="key-id", secret_access_key="secret")
    )


async def test_the_client_trusts_what_the_policy_trusts_while_the_setting_is_on(
    listener: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    endpoint, certificate = listener
    monkeypatch.setenv("MYRM_TLS_STRICT", "0")
    monkeypatch.setattr(ssl, "create_default_context", _trusting(certificate))

    assert await _strategy(endpoint).check_connection() is True


async def test_the_client_keeps_its_own_trust_while_the_setting_is_off(
    listener: tuple[str, Path], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    endpoint, certificate = listener
    monkeypatch.delenv("MYRM_TLS_STRICT", raising=False)
    monkeypatch.setattr(ssl, "create_default_context", _trusting(certificate))

    assert await _strategy(endpoint).check_connection() is False
    assert "CERTIFICATE_VERIFY_FAILED" in caplog.text


async def test_a_peer_the_policy_does_not_trust_is_still_rejected_while_the_setting_is_on(
    listener: tuple[str, Path], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    endpoint, _ = listener
    monkeypatch.setenv("MYRM_TLS_STRICT", "0")

    assert await _strategy(endpoint).check_connection() is False
    assert "CERTIFICATE_VERIFY_FAILED" in caplog.text
