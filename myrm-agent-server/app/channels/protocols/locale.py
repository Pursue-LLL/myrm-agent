"""Locale resolution protocol for channel ingress.

[INPUT]
- channels.types::InboundMessage (POS: inbound message with metadata)

[OUTPUT]
- LocaleProvider: Protocol for resolving user locale at ingress

[POS]
Framework contract for business layer to inject user language preference
(from UserConfig, platform API, etc.) into channel message metadata.
"""

from __future__ import annotations

from typing import Protocol

from app.channels.types import InboundMessage


class LocaleProvider(Protocol):
    """Resolve locale for an inbound channel message."""

    async def resolve_locale(self, msg: InboundMessage) -> str:
        """Return the sender's normalized locale: en, zh-CN, zh-TW or another BCP-47 tag."""
        ...
