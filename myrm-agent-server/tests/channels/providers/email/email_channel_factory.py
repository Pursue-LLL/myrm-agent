"""A configured ``EmailChannel``, minimal messages and a parse helper for the mail channel tests."""

from __future__ import annotations

import email.mime.text
import email.utils

from app.channels.providers.email import EmailChannel
from app.channels.types import InboundMessage

_PLAIN = b"text/plain; charset=utf-8"
_BODY = "正文 Body".encode()


def make_channel() -> EmailChannel:
    return EmailChannel(
        imap_host="imap.example.com",
        imap_user="bot@example.com",
        imap_password="secret",
        smtp_host="smtp.example.com",
        smtp_user="bot@example.com",
        smtp_password="secret",
    )


def raw_mail(uid: int) -> bytes:
    """A plain-text message from ``sender@example.com`` whose body (``Body <uid>``) and subject name *uid*."""
    msg = email.mime.text.MIMEText(f"Body {uid}", "plain")
    msg["From"] = "sender@example.com"
    msg["To"] = "bot@example.com"
    msg["Subject"] = f"Subject {uid}"
    msg["Message-ID"] = email.utils.make_msgid()
    return msg.as_bytes()


def raw_message(headers: dict[str, bytes] | None = None, *, body: bytes = _BODY, content_type: bytes = _PLAIN) -> bytes:
    """The bytes of a message from ``sender@example.com``, written as given so that raw UTF-8 and odd spellings survive.

    *headers* add to or replace the defaults (From, To, Subject, Message-ID).
    """
    merged = {
        "From": b"sender@example.com",
        "To": b"bot@example.com",
        "Subject": b"Hello",
        "Message-ID": b"<m1@example.com>",
        **(headers or {}),
    }
    lines = [name.encode() + b": " + value for name, value in merged.items()]
    return b"\r\n".join([*lines, b"MIME-Version: 1.0", b"Content-Type: " + content_type, b"", body])


def parse_inbound(raw: bytes) -> InboundMessage:
    """What the channel makes of *raw*; the message must not be filtered out."""
    result = make_channel()._parse_email(raw, uid=1)
    assert result is not None
    return result
