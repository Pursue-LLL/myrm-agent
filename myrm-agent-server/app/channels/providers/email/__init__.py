"""Email channel provider package (IMAP inbound + SMTP outbound).

[INPUT]
- channels.providers.email.channel::EmailChannel (POS: Email bidirectional messaging Channel)

[OUTPUT]
- EmailChannel: package facade for the registry's lazy loader

[POS]
Package facade; the implementation lives in ``channel.py`` (lifecycle, SMTP/IMAP), ``inbound.py`` (RFC 822 parsing)
and ``forward.py`` (forwarded-email detection).
"""

from .channel import EmailChannel

__all__ = ["EmailChannel"]
