"""A real IMAP/SMTP server for tests that need a mailbox no scripted fake can stand in for: GreenMail in Docker, on loopback only.

[INPUT]
- Docker and the ``greenmail/standalone`` image (pulled on first use)
- tests/support/self_signed_tls.py: the certificate the server presents (valid for ``127.0.0.1``)

[OUTPUT]
- Mailbox: the ports of a running server and the PEM bundle that trusts it
- running_mailbox: start the server, wait until it answers over TLS, remove the container afterwards
- deliver: put a message into a mailbox the way another sender would
- messages_of: every message of one user's inbox, parsed

[POS]
Server pytest-only helper of the live tests of the imap-smtp-email skill. The server accepts any login and creates the
mailbox of an address when mail first arrives for it. SMTP over implicit TLS needs the skill script's port 465, so that
host port is taken for the run; a test that cannot have it is skipped, not failed.
"""

from __future__ import annotations

import email
import email.message
import email.policy
import imaplib
import shutil
import smtplib
import socket
import ssl
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from tests.support.self_signed_tls import self_signed_certificate

IMAGE = "greenmail/standalone:latest"
SMTP_TLS_HOST_PORT = 465
_KEYSTORE_PASSWORD = b"changeit"
_START_TIMEOUT_SECONDS = 120
_SERVER_OPTIONS = (
    "-Dgreenmail.setup.test.all -Dgreenmail.hostname=0.0.0.0 -Dgreenmail.auth.disabled "
    "-Dgreenmail.tls.keystore.file=/keystore/greenmail.p12 -Dgreenmail.tls.keystore.password=changeit"
)


@dataclass(frozen=True)
class Mailbox:
    """A running server: ``host`` for IMAP over TLS (``imap_port``) and SMTP over TLS (465), ``smtp_port`` for plain delivery."""

    host: str
    imap_port: int
    smtp_port: int
    ca_bundle: Path
    certificate: Path


def _free_port() -> int:
    with socket.create_server(("127.0.0.1", 0)) as server:
        return int(server.getsockname()[1])


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=_START_TIMEOUT_SECONDS, check=False)


def _write_keystore(directory: Path) -> Path:
    """The server's certificate as the PKCS#12 keystore GreenMail loads."""
    certificate_file, key_file = self_signed_certificate(directory)
    certificate = x509.load_pem_x509_certificate(certificate_file.read_bytes())
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    encryption = serialization.BestAvailableEncryption(_KEYSTORE_PASSWORD)
    keystore = directory / "greenmail.p12"
    keystore.write_bytes(pkcs12.serialize_key_and_certificates(b"greenmail", key, certificate, None, encryption))
    keystore.chmod(0o644)
    directory.chmod(0o755)
    return certificate_file


def _wait_until_serving(host: str, port: int, certificate: Path) -> None:
    """Ready means a TLS login works: the port opens before the server is able to answer."""
    context = ssl.create_default_context(cafile=str(certificate))
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=5) as conn:
                conn.login("probe@localhost", "probe")
            return
        except (OSError, imaplib.IMAP4.error):
            time.sleep(1)
    raise TimeoutError(f"GreenMail did not answer over TLS on {host}:{port} within {_START_TIMEOUT_SECONDS}s")


@contextmanager
def running_mailbox(directory: Path) -> Iterator[Mailbox]:
    """Start the server with a fresh certificate in *directory*; skip the test when Docker or port 465 is not available."""
    if shutil.which("docker") is None:
        pytest.skip("The docker command is required for the real mail server")
    daemon = _docker("info")
    if daemon.returncode != 0:
        pytest.skip(f"The Docker daemon is not reachable: {daemon.stderr.strip()[-300:]}")
    certificate = _write_keystore(directory)
    ca_bundle = directory / "ca-bundle.pem"
    # The bundle replaces the default trust store of every client that reads SSL_CERT_FILE, the model provider's included.
    ca_bundle.write_text(Path(certifi.where()).read_text() + "\n" + certificate.read_text())
    host, imap_port, smtp_port = "127.0.0.1", _free_port(), _free_port()
    name = f"myrm-mail-test-{uuid.uuid4().hex[:8]}"
    started = _docker(
        "run", "-d", "--rm", "--name", name,
        "-p", f"{host}:{imap_port}:3993", "-p", f"{host}:{smtp_port}:3025", "-p", f"{host}:{SMTP_TLS_HOST_PORT}:3465",
        "-v", f"{directory}:/keystore:ro", "-e", f"GREENMAIL_OPTS={_SERVER_OPTIONS}", IMAGE,
    )  # fmt: skip
    if started.returncode != 0:
        pytest.skip(
            f"The mail server could not start (port {SMTP_TLS_HOST_PORT} taken, or no image): {started.stderr.strip()[-300:]}"
        )
    try:
        _wait_until_serving(host, imap_port, certificate)
        yield Mailbox(host, imap_port, smtp_port, ca_bundle, certificate)
    finally:
        _docker("rm", "-f", name)


def deliver(mailbox: Mailbox, message: email.message.EmailMessage) -> None:
    with smtplib.SMTP(mailbox.host, mailbox.smtp_port, timeout=15) as server:
        server.send_message(message)


def messages_of(mailbox: Mailbox, user: str) -> list[email.message.EmailMessage]:
    """Every message of *user*'s inbox, oldest first."""
    context = ssl.create_default_context(cafile=str(mailbox.certificate))
    with imaplib.IMAP4_SSL(mailbox.host, mailbox.imap_port, ssl_context=context, timeout=15) as conn:
        conn.login(user, "pw")
        conn.select("INBOX", readonly=True)
        _, found = conn.uid("search", None, "ALL")
        uids = found[0].split() if found and found[0] else []
        messages: list[email.message.EmailMessage] = []
        for uid in uids:
            _, data = conn.uid("fetch", uid, "(RFC822)")
            raw = data[0][1] if data and isinstance(data[0], tuple) else b""
            parsed = email.message_from_bytes(raw, policy=email.policy.default)
            assert isinstance(parsed, email.message.EmailMessage)
            messages.append(parsed)
        return messages
