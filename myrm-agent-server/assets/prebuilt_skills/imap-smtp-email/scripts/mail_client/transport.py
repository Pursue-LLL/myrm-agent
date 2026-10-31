"""IMAP/SMTP transport for the imap-smtp-email skill script: environment config, verified TLS connections, error exits.

[INPUT]
- Process env EMAIL_IMAP_HOST, EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD, EMAIL_IMAP_PORT (default 993)
- Process env EMAIL_SMTP_HOST, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_SMTP_PORT (default 587); SMTP falls back to the IMAP values
- Process env SSL_CERT_FILE (optional): PEM bundle that replaces the default trust store, for servers signed by a private CA

[OUTPUT]
- fail: print a JSON error on stdout and exit
- get_smtp_config: SMTP host, port, user and password
- connect_imap: logged-in IMAP4_SSL connection (RFC 2971 ID sent for 163/NetEase)
- deliver: send one message over SMTP (implicit TLS on 465, STARTTLS otherwise)

[POS]
Transport half of the email_manager.py facade. Every connection verifies the server certificate and times out on a
silent server; a rejected certificate exits with a hint instead of a stack trace.
"""

from __future__ import annotations

import email.mime.multipart
import imaplib
import json
import os
import smtplib
import ssl
import sys
from typing import NoReturn


def fail(message: str, *, code: int = 1) -> NoReturn:
    print(json.dumps({"error": message}))
    sys.exit(code)


def _require_env(key: str, default: str = "") -> str:
    value = os.environ.get(key, default).strip()
    if not value:
        fail(f"Environment variable {key} is not set")
    return value


def _get_imap_config() -> tuple[str, int, str, str]:
    host = _require_env("EMAIL_IMAP_HOST")
    port = int(os.environ.get("EMAIL_IMAP_PORT", "993").strip() or "993")
    user = _require_env("EMAIL_IMAP_USER")
    password = _require_env("EMAIL_IMAP_PASSWORD")
    return host, port, user, password


def get_smtp_config() -> tuple[str, int, str, str]:
    host = os.environ.get("EMAIL_SMTP_HOST", "").strip()
    if not host:
        imap_host = _require_env("EMAIL_IMAP_HOST")
        host = imap_host.replace("imap.", "smtp.")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "587").strip() or "587")
    user = os.environ.get("EMAIL_SMTP_USER", "").strip() or _require_env("EMAIL_IMAP_USER")
    password = os.environ.get("EMAIL_SMTP_PASSWORD", "").strip() or _require_env("EMAIL_IMAP_PASSWORD")
    return host, port, user, password


def _send_imap_id(conn: imaplib.IMAP4_SSL) -> None:
    """Send RFC 2971 IMAP ID command. Required by 163/NetEase after LOGIN."""
    try:
        conn.xatom(
            "ID",
            '("name" "myrm-agent" "version" "1" "vendor" "myrm" "support-email" "noreply@myrm.sh")',
        )
    except Exception:
        pass


_SOCKET_TIMEOUT = 30

_CERTIFICATE_HINT = (
    "If this server is signed by a private or corporate CA, set SSL_CERT_FILE to a PEM bundle that contains that CA "
    "in the environment the agent server runs in; the bundle replaces the default trust store, so it must also hold "
    "every public CA this script still has to trust. Do not disable certificate verification."
)


def _fail_certificate(service: str, exc: ssl.SSLCertVerificationError) -> NoReturn:
    fail(f"{service} server certificate verification failed: {exc.verify_message}. {_CERTIFICATE_HINT}")


def connect_imap() -> imaplib.IMAP4_SSL:
    host, port, user, password = _get_imap_config()
    try:
        conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=_SOCKET_TIMEOUT)
        conn.login(user, password)
        _send_imap_id(conn)
        return conn
    except imaplib.IMAP4.error as exc:
        fail(f"IMAP authentication failed: {exc}")
    except ssl.SSLCertVerificationError as exc:
        _fail_certificate("IMAP", exc)
    except (OSError, TimeoutError) as exc:
        fail(f"IMAP connection failed: {exc}")


def deliver(msg: email.mime.multipart.MIMEMultipart, host: str, port: int, user: str, password: str) -> None:
    """Send *msg* over an SMTP connection whose server certificate is verified; exit with an error when it fails."""
    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=_SOCKET_TIMEOUT, context=context) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=_SOCKET_TIMEOUT) as server:
                server.starttls(context=context)
                server.login(user, password)
                server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        fail(f"SMTP authentication failed: {exc}")
    except ssl.SSLCertVerificationError as exc:
        _fail_certificate("SMTP", exc)
    except (smtplib.SMTPException, OSError) as exc:
        fail(f"SMTP send failed: {exc}")
