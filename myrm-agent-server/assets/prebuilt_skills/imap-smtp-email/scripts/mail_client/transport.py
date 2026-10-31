"""IMAP/SMTP transport for the imap-smtp-email skill script: environment config, verified TLS connections, error exits.

[INPUT]
- Process env EMAIL_IMAP_HOST, EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD, EMAIL_IMAP_PORT (default 993)
- Process env EMAIL_SMTP_HOST, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_SMTP_PORT (default 587); SMTP falls back to the IMAP values
- Process env SSL_CERT_FILE (optional): PEM bundle that replaces the default trust store, for servers signed by a private CA

[OUTPUT]
- fail: print a JSON error on stdout and exit
- get_smtp_config: SMTP host, port, user and password
- connect_imap: logged-in IMAP4_SSL connection (RFC 2971 ID sent for 163/NetEase)
- imap_quote: search text as an IMAP quoted string; control characters (a line break would start another command) and
  non-ASCII text are refused
- select_folder: open a mailbox; a name that is not ASCII, or that the server refuses, exits with a pointer to `folders`
- parse_uids: a comma-separated UID list whose items consist only of digits, `:` and `*`
- json_errors: a failure after the connection is up, or a message the standard library refuses to build or parse,
  becomes a JSON error instead of a stack trace
- deliver: send one message over SMTP (implicit TLS on 465, STARTTLS otherwise)

[POS]
Transport half of the email_manager.py facade. Every connection verifies the server certificate and times out on a
silent server; a rejected certificate exits with a hint instead of a stack trace. Text that reaches the IMAP server is
quoted or validated here, because imaplib joins string arguments into the command line unchecked and encodes them as
ASCII.
"""

from __future__ import annotations

import email.errors
import email.mime.multipart
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
from collections.abc import Iterator
from contextlib import contextmanager
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


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
# Mailbox names sent as they are: none of the characters that end or split an IMAP argument. Anything else is quoted.
_PLAIN_MAILBOX = re.compile(r"[A-Za-z0-9._/\[\]&+-]+")
_UID_SET = re.compile(r"[0-9:*]+")


def imap_quote(text: str) -> str:
    """Quote search *text* as an IMAP string; refuse a control character (it would end the command line) and non-ASCII."""
    if _CONTROL_CHARS.search(text):
        fail("IMAP arguments must not contain control characters")
    if not text.isascii():
        fail(
            "This script sends only ASCII search text to the IMAP server; "
            "list recent messages with `check` and filter them by subject or sender yourself"
        )
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def select_folder(conn: imaplib.IMAP4_SSL, folder: str, *, readonly: bool) -> None:
    """Open *folder*. A server that refuses it leaves the session unselected, so exit with the server's reason."""
    if _PLAIN_MAILBOX.fullmatch(folder):
        mailbox = folder
    elif folder.isascii():
        mailbox = imap_quote(folder)
    else:
        fail(f"Folder '{folder}' is not ASCII: use the name exactly as the `folders` command lists it")
    status, data = conn.select(mailbox, readonly=readonly)
    if status != "OK":
        reason = data[0].decode("utf-8", errors="replace") if data and isinstance(data[0], bytes) else status
        fail(f"Mailbox '{folder}' could not be opened: {reason}. Run the `folders` command to list the available folders")


def parse_uids(text: str) -> list[str]:
    """Split a comma-separated UID list. An item holds only digits, `:` and `*`, so no free text reaches the command line."""
    uids = [item.strip() for item in text.split(",") if item.strip()]
    if not uids:
        fail("At least one UID is required")
    for uid in uids:
        if not _UID_SET.fullmatch(uid):
            fail(f"Invalid UID '{uid}': use digits, optionally as a range such as 5:9")
    return uids


@contextmanager
def json_errors(command: str) -> Iterator[None]:
    """Turn a failure after the connection is up into the script's JSON error instead of a stack trace.

    ``MessageError`` is what the standard library raises when it refuses to build or parse a message, for example a
    header value that contains a line break.
    """
    try:
        yield
    except (imaplib.IMAP4.error, OSError, email.errors.MessageError) as exc:
        fail(f"Email command '{command}' failed: {exc}")


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
