"""A configured ``EmailChannel`` and a minimal message for the mail channel tests."""

from __future__ import annotations

import email.mime.text
import email.utils

from app.channels.providers.email import EmailChannel


def make_channel(**overrides: str) -> EmailChannel:
    defaults = {
        "imap_host": "imap.example.com",
        "imap_user": "bot@example.com",
        "imap_password": "secret",
        "smtp_host": "smtp.example.com",
        "smtp_user": "bot@example.com",
        "smtp_password": "secret",
    }
    defaults.update(overrides)
    return EmailChannel(**defaults)  # type: ignore[arg-type]


def raw_mail(uid: int) -> bytes:
    """A plain-text message from ``sender@example.com`` whose body (``Body <uid>``) and subject name *uid*."""
    msg = email.mime.text.MIMEText(f"Body {uid}", "plain")
    msg["From"] = "sender@example.com"
    msg["To"] = "bot@example.com"
    msg["Subject"] = f"Subject {uid}"
    msg["Message-ID"] = email.utils.make_msgid()
    return msg.as_bytes()
