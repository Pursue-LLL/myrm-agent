"""Internationalization for channel static messages.

[INPUT]
- channels.types::InboundMessage (POS: locale in metadata)
- myrm_agent_harness.utils.locale::normalize_locale / resolve_locale (POS: BCP-47 normalization)

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


def _locale_from_meta(meta: dict[str, object], channel: str | None) -> str:
    """Resolve the effective locale from a message metadata dict.

    Priority follows :func:`myrm_agent_harness.utils.locale.resolve_locale`:
    explicit ``metadata.locale`` wins over ``platform_locale``/``language_code``,
    with the channel's platform default as fallback.
    """
    platform_locale = meta.get("platform_locale")
    if not platform_locale:
        language_code = meta.get("language_code")
        if language_code:
            platform_locale = language_code
    platform_val = str(platform_locale) if platform_locale else None
    locale_val = meta.get("locale")
    metadata_val = str(locale_val) if locale_val else None
    return resolve_locale(
        metadata_locale=metadata_val,
        platform_locale=platform_val,
        channel=channel,
    )


def get_locale_from_metadata(metadata: dict[str, object] | None) -> str:
    """Resolve locale from a metadata dict (inbound/outbound messages)."""
    from myrm_agent_harness.utils.locale import normalize_locale

    if not metadata:
        return normalize_locale(None)
    return _locale_from_meta(metadata, None)


def resolve_message_locale(msg: InboundMessage) -> str:
    """Resolve locale from inbound message metadata."""
    return _locale_from_meta(msg.metadata or {}, msg.channel)


def get_text(msg: InboundMessage, key: str, **kwargs: Any) -> str:
    """Translate a catalog key using the locale from an InboundMessage."""
    locale = resolve_message_locale(msg)
    return str(channel_t(locale, key, **kwargs))


__all__ = [
    "add_locale_root",
    "channel_t",
    "get_locale_from_metadata",
    "get_text",
    "resolve_message_locale",
]
