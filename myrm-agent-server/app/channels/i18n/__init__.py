"""Internationalization for channel static messages.

[INPUT]
- channels.types::InboundMessage (POS: locale in metadata)
- utils.locale::LocaleResolver helpers (POS: normalization)

[OUTPUT]
- channel_t: Translate by locale string
- get_text: Translate using InboundMessage locale
- resolve_message_locale: Resolve locale from message metadata
- add_locale_root: Register a new directory containing .ftl files

[POS]
Provides multi-language support for gateway slash command replies and
system-generated channel messages (not Agent LLM output).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from myrm_agent_harness.utils.locale import resolve_locale

from .engine import add_locale_root, channel_t

if TYPE_CHECKING:
    from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)


def get_locale_from_metadata(metadata: dict[str, object] | None) -> str:
    """Resolve locale from a metadata dict (inbound/outbound messages)."""
    from myrm_agent_harness.utils.locale import normalize_locale

    if not metadata:
        return normalize_locale(None)

    platform_locale = metadata.get("platform_locale")
    if not platform_locale:
        language_code = metadata.get("language_code")
        if language_code:
            platform_locale = language_code

    platform_val = str(platform_locale) if platform_locale else None
    locale_val = metadata.get("locale")
    metadata_val = str(locale_val) if locale_val else None
    return resolve_locale(
        metadata_locale=metadata_val,
        platform_locale=platform_val,
        channel=None,
    )


def resolve_message_locale(msg: InboundMessage) -> str:
    """Resolve locale from inbound message metadata."""
    meta = msg.metadata or {}
    platform_locale = meta.get("platform_locale")
    if not platform_locale:
        language_code = meta.get("language_code")
        if language_code:
            platform_locale = language_code
    platform_val = str(platform_locale) if platform_locale else None
    metadata_locale = meta.get("locale")
    metadata_val = str(metadata_locale) if metadata_locale else None
    return resolve_locale(
        metadata_locale=metadata_val,
        platform_locale=platform_val,
        channel=msg.channel,
    )


def get_text(msg: InboundMessage, key: str, **kwargs: Any) -> str:
    """Translate a catalog key using the locale from an InboundMessage."""
    locale = resolve_message_locale(msg)
    return channel_t(locale, key, **kwargs)


__all__ = [
    "add_locale_root",
    "channel_t",
    "get_locale_from_metadata",
    "get_text",
    "resolve_message_locale",
]
