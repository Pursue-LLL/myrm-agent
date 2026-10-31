"""A configured ``EmailChannel`` for the mail channel tests."""

from __future__ import annotations

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
