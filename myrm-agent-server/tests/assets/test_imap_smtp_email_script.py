"""The imap-smtp-email skill script verifies every server certificate and trusts a private CA only through SSL_CERT_FILE.

The script runs in a child process the server's TLS policy never reaches. Each test starts it against a loopback
listener whose certificate is its own issuer: the real handshake has to fail by default and pass once SSL_CERT_FILE
names that certificate. Implicit-TLS SMTP needs the privileged port 465, so every call site is also checked in process
against ``autospec`` doubles of the stdlib clients, where a keyword they do not accept raises ``TypeError``.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py run as a subprocess; mail_client.transport imported
- tests/support/email_skill_script.py: the loopback listener and the script runner
- tests/assets/conftest.py: the loopback certificate and the script import path
- tests/support/bounded_wait.py: the timeout bound

[OUTPUT]
- Fails when a connection of the script skips certificate verification, ignores SSL_CERT_FILE, passes the stdlib TLS
  client a keyword it rejects, or waits without a bound

[POS]
Subprocess and handshake test of the prebuilt skill script, the counterpart of ``test_tls_single_trust_source.py``,
which only checks that each call passes a context.
"""

from __future__ import annotations

import importlib
import json
import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from unittest.mock import create_autospec, patch

import pytest

from tests.support.bounded_wait import assert_bounded_wait
from tests.support.email_skill_script import run_email_script, serve_sessions


def _imap_session(conn: socket.socket, context: ssl.SSLContext) -> None:
    """Implicit TLS, then greet, answer CAPABILITY and refuse LOGIN: reaching LOGIN proves the handshake went through."""
    stream = context.wrap_socket(conn, server_side=True).makefile("rwb")
    stream.write(b"* OK IMAP4rev1 ready\r\n")
    stream.flush()
    for raw in stream:
        tag, _, rest = raw.decode().rstrip("\r\n").partition(" ")
        verb = rest.split(" ", 1)[0].upper()
        if verb == "CAPABILITY":
            stream.write(b"* CAPABILITY IMAP4rev1\r\n")
        stream.write(
            f"{tag} NO [AUTHENTICATIONFAILED] rejected\r\n".encode() if verb == "LOGIN" else f"{tag} OK done\r\n".encode()
        )
        stream.flush()


def _smtp_session(conn: socket.socket, context: ssl.SSLContext) -> None:
    """Plain greeting, STARTTLS upgrade, then refuse AUTH: reaching AUTH proves the handshake went through."""
    stream = conn.makefile("rwb")
    stream.write(b"220 ready\r\n")
    stream.flush()
    secured = False
    # ``readline`` per turn, not ``for raw in stream``: the stream is replaced by the TLS one after STARTTLS.
    while raw := stream.readline():
        verb = raw.decode().split(" ", 1)[0].strip().upper()
        if verb == "STARTTLS":
            stream.write(b"220 go ahead\r\n")
            stream.close()
            stream = context.wrap_socket(conn, server_side=True).makefile("rwb")
            secured = True
            continue
        if verb == "EHLO":
            stream.write(b"250-ready\r\n250 AUTH PLAIN\r\n" if secured else b"250-ready\r\n250 STARTTLS\r\n")
        elif verb == "AUTH":
            stream.write(b"535 5.7.8 rejected\r\n")
        else:
            stream.write(b"221 bye\r\n")
        stream.flush()


def _run_script(tmp_path: Path, args: list[str], *, port: int, protocol: str, trust: Path | None) -> str:
    """Run the script; it has to fail, and its JSON ``error`` is returned."""
    proc = run_email_script(tmp_path, args, port=port, protocol=protocol, trust=trust)
    assert proc.returncode == 1, proc.stderr
    return str(json.loads(proc.stdout)["error"])


_PROTOCOLS = {
    "imap": (_imap_session, ["check"], "IMAP"),
    "smtp": (_smtp_session, ["send", "--to", "bob@example.test", "--subject", "s", "--body", "b"], "SMTP"),
}


@pytest.mark.parametrize("protocol", _PROTOCOLS)
def test_a_certificate_no_default_store_accepts_is_refused_with_a_hint(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], protocol: str
) -> None:
    session, args, service = _PROTOCOLS[protocol]
    with serve_sessions(session, listener_tls[0]) as port:
        error = _run_script(tmp_path, args, port=port, protocol=protocol, trust=None)

    assert error.startswith(f"{service} server certificate verification failed: ")
    assert "SSL_CERT_FILE" in error
    assert "Do not disable certificate verification" in error


@pytest.mark.parametrize("protocol", _PROTOCOLS)
def test_ssl_cert_file_lets_the_handshake_through_to_the_login(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], protocol: str
) -> None:
    session, args, service = _PROTOCOLS[protocol]
    with serve_sessions(session, listener_tls[0]) as port:
        error = _run_script(tmp_path, args, port=port, protocol=protocol, trust=listener_tls[1])

    assert error.startswith(f"{service} authentication failed")


@pytest.mark.usefixtures("skill_modules")
def test_every_connection_is_bounded_and_verifies_the_peer_through_keywords_the_stdlib_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subprocess tests above cover IMAP and STARTTLS; this one also reaches implicit TLS (port 465)."""
    transport = importlib.import_module("mail_client.transport")
    monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("EMAIL_IMAP_USER", "agent@example.test")
    monkeypatch.setenv("EMAIL_IMAP_PASSWORD", "secret")
    starttls_server = create_autospec(smtplib.SMTP, instance=True)

    with (
        patch("imaplib.IMAP4_SSL", autospec=True) as imap,
        patch("smtplib.SMTP_SSL", autospec=True) as smtp_ssl,
        patch("smtplib.SMTP", autospec=True) as smtp,
    ):
        smtp.return_value.__enter__.return_value = starttls_server
        transport.connect_imap()
        transport.deliver(MIMEMultipart(), "smtp.example.test", 465, "agent@example.test", "secret")
        transport.deliver(MIMEMultipart(), "smtp.example.test", 587, "agent@example.test", "secret")

    connections = {
        "imap": (imap.call_args.kwargs["ssl_context"], imap.call_args.kwargs["timeout"]),
        "smtp over implicit tls": (smtp_ssl.call_args.kwargs["context"], smtp_ssl.call_args.kwargs["timeout"]),
        "smtp over starttls": (starttls_server.starttls.call_args.kwargs["context"], smtp.call_args.kwargs["timeout"]),
    }
    for context, timeout in connections.values():
        assert context.verify_mode is ssl.CERT_REQUIRED
        assert context.check_hostname is True
        assert_bounded_wait(timeout)
